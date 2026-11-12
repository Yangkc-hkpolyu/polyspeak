# PolySpeak Voice Check — fine-tuning experiment

This is an experimental local QLoRA adapter for Qwen2.5-1.5B-Instruct. It generates short English practice advice from structured voice-check metrics; it does not receive recordings or transcripts and does not assess pronunciation or intelligibility.

## Training

- Base: `Qwen/Qwen2.5-1.5B-Instruct`, loaded in 4-bit NF4.
- LoRA: rank 8 on the query and value projections, 1,089,536 trainable parameters.
- Training: 608 synthetic, rule-generated examples, two epochs; RTX 4060 Laptop GPU, observed peak PyTorch allocation about 2.38 GiB.
- Data: `data/train.jsonl`, with separate validation and test files. These examples are not real learner recordings or teacher annotations. Version 2 was designed after investigating failures of an earlier version.

## Evaluation and limitations

The file `evaluation_v2.json` contains comparisons on 38 stratified synthetic test cases, two from each of 19 groups. These tests use new generated inputs and split-specific wording, but share the same synthetic generation process as training, which was revised after earlier observations. They are not real-world or fully independent generalization evidence.

The comparison heuristics flagged 27/38 base-model outputs and 3/38 adapter outputs. The adapter's three flags involved an incorrect low-volume claim. The separate runtime filter rejected those three outputs and accepted 35/38; none of those accepted outputs triggered the same limited automated flags. The filter is heuristic, can miss errors or reject useful advice, and does not prove correctness. One accepted answer omitted a recording-quality cue under the prototype's threshold rules.

Before relying on this in practice, evaluate with consented recordings, different accents and microphones, noisy environments, and human reviewers. Never interpret this model's feedback as an official exam score. Audio volume is not pronunciation accuracy.

## Contents

- `adapter/` — LoRA weights, tokenizer files and training summary.
- `base/` — downloaded base weights and its license.
- `deps/` — isolated Windows/Python 3.12 inference dependencies. Existing project PyTorch is still required.
- `data/` — synthetic data and its generation notes.
- `inference_worker.py` — offline, local inference and conservative output checks.
- `train.py`, `evaluate.py`, `eval_samples_v2.jsonl`, `evaluation_v2.json` — experiment scripts and held-out synthetic comparisons.

The desktop project locates this directory via `speaking-models/voice-coach-config.json`. If this folder is moved or deleted, update that configuration or the optional local-model advice becomes unavailable; the rule-based Voice check remains available. The bundled base and dependencies occupy about 3.3 GB.
