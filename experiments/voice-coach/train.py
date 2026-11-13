"""Small, local QLoRA experiment for evidence-grounded Voice Check advice."""
import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'deps'))

import torch
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


def training_example(row, tokenizer, limit):
    messages = [
        {'role': 'system', 'content': row['instruction']},
        {'role': 'user', 'content': json.dumps(row['input'], ensure_ascii=False, sort_keys=True)},
    ]
    prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    full = tokenizer.apply_chat_template(messages + [{'role': 'assistant', 'content': row['output']}], tokenize=False, add_generation_prompt=False)
    prompt_ids = tokenizer(prompt, add_special_tokens=False)['input_ids']
    full_ids = tokenizer(full, add_special_tokens=False)['input_ids']
    if full_ids[:len(prompt_ids)] != prompt_ids:
        raise ValueError('Prompt and response tokenization do not match')
    if len(full_ids) > limit:
        raise ValueError(f'Example has {len(full_ids)} tokens, exceeds limit {limit}')
    return {'input_ids': full_ids, 'labels': [-100] * len(prompt_ids) + full_ids[len(prompt_ids):]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default=str(ROOT / 'base'))
    parser.add_argument('--data', default=str(ROOT / 'data' / 'train.jsonl'))
    parser.add_argument('--output', default=str(ROOT / 'adapter'))
    parser.add_argument('--epochs', type=int, default=2)
    parser.add_argument('--accumulation', type=int, default=4)
    parser.add_argument('--max-tokens', type=int, default=512)
    parser.add_argument('--learning-rate', type=float, default=0.0002)
    parser.add_argument('--max-examples', type=int, default=0)
    args = parser.parse_args()
    if not torch.cuda.is_available():
        raise RuntimeError('A CUDA-enabled GPU is required for this experiment.')
    random.seed(431)
    torch.manual_seed(431)
    torch.cuda.manual_seed_all(431)
    torch.set_num_threads(4)
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    model_dir = str(Path(args.base).resolve())
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
    quantization = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type='nf4', bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    model = AutoModelForCausalLM.from_pretrained(model_dir, quantization_config=quantization, torch_dtype=dtype, device_map={'': 0}, local_files_only=True)
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    model = get_peft_model(model, LoraConfig(r=8, lora_alpha=16, lora_dropout=0.05, bias='none', task_type='CAUSAL_LM', target_modules=['q_proj', 'v_proj']))
    rows = [json.loads(line) for line in Path(args.data).read_text(encoding='utf-8').splitlines() if line.strip()]
    if args.max_examples:
        rows = rows[:args.max_examples]
    examples = [training_example(row, tokenizer, args.max_tokens) for row in rows]
    if not examples:
        raise ValueError('Training dataset is empty')
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    print(f'Loaded {len(examples)} examples; trainable parameters={trainable}; dtype={dtype}', flush=True)
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.learning_rate)
    losses = []
    model.train()
    for epoch in range(args.epochs):
        random.shuffle(examples)
        optimizer.zero_grad(set_to_none=True)
        window_loss = 0.0
        for index, example in enumerate(examples):
            inputs = torch.tensor([example['input_ids']], dtype=torch.long, device='cuda')
            labels = torch.tensor([example['labels']], dtype=torch.long, device='cuda')
            output = model(input_ids=inputs, attention_mask=torch.ones_like(inputs), labels=labels)
            loss = output.loss
            if not math.isfinite(loss.item()):
                raise RuntimeError(f'Non-finite training loss at epoch {epoch + 1}, example {index + 1}')
            window_loss += float(loss.item())
            (loss / args.accumulation).backward()
            if (index + 1) % args.accumulation == 0 or index + 1 == len(examples):
                torch.nn.utils.clip_grad_norm_((p for p in model.parameters() if p.requires_grad), 1.0)
                optimizer.step()
                optimizer.zero_grad(set_to_none=True)
                divisor = args.accumulation if (index + 1) % args.accumulation == 0 else (index + 1) % args.accumulation
                average = window_loss / divisor
                losses.append(average)
                window_loss = 0.0
                if len(losses) % 10 == 0 or index + 1 == len(examples):
                    print(f'epoch {epoch + 1}/{args.epochs} examples {index + 1}/{len(examples)} loss {average:.3f} GPU_peak_GB {torch.cuda.max_memory_allocated()/1024**3:.2f}', flush=True)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(output, safe_serialization=True)
    tokenizer.save_pretrained(output)
    (output / 'training_summary.json').write_text(json.dumps({'method': 'QLoRA NF4', 'base': 'Qwen/Qwen2.5-1.5B-Instruct', 'samples': len(examples), 'epochs': args.epochs, 'trainable_parameters': trainable, 'synthetic_training_data': True, 'losses': losses, 'peak_gpu_gb': round(torch.cuda.max_memory_allocated()/1024**3, 3)}, indent=2), encoding='utf-8')
    print(f'Saved adapter to {output}', flush=True)


if __name__ == '__main__':
    main()
