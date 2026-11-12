"""Compare a local base model and LoRA on held-out synthetic examples.

This checks observable formatting and some unsupported claims. It does not
measure pedagogical quality, fairness or pronunciation accuracy. Every raw
answer is retained for manual review; never use real student data without an
appropriate privacy and evaluation plan.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def load_examples(path: Path, limit: int):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit:
        rows = rows[:limit]
    if not rows:
        raise ValueError("No held-out examples found")
    for row in rows:
        if not isinstance(row.get("instruction"), str) or not isinstance(row.get("input"), dict):
            raise ValueError("Each row requires instruction (string) and input (object)")
    return rows


def assess(text: str, data: dict):
    """Conservative heuristics, intended to flag examples for human review."""
    text = text.strip()
    lower = text.lower()
    result = {"empty": not bool(text), "too_long": len(text) > 600,
              "format_flag": bool(re.search(r"(^|\n)\s*(?:#{1,6}\s|[-*]\s|\d+[.)]\s)", text)),
              "pronunciation_claim": False, "unsupported_pace": False,
              "unsupported_pause": False, "wpm_number_mismatch": False,
              "pause_number_mismatch": False, "unsupported_exam_score": False,
              "contradictory_low_level_advice": False, "contradictory_clipping_claim": False,
              "unsupported_clarity_claim": False, "unsupported_noise_claim": False,
              "unsupported_personal_inference": False}
    # A clear negation is not treated as a claim. This is a heuristic, not an
    # entailment model, and ambiguous cases require human review.
    if not data.get("pronunciation_assessed", False):
        for sentence in re.split(r"(?<=[.!?])\s+", lower):
            negated = re.search(r"\b(?:not (?:been )?(?:assessed|evaluated|measured|available)|cannot (?:assess|evaluate|measure)|can't (?:assess|evaluate|measure)|unable to (?:assess|evaluate|measure)|not enough (?:information|data|evidence) to (?:assess|evaluate|measure))\b", sentence)
            if re.search(r"\b(pronunciation|pronounced|pronounce|mispronounc|accent|articulation)\w*\b", sentence):
                if not negated:
                    result["pronunciation_claim"] = True
            if re.search(r"\b(?:you speak clearly|your speech is clear|hard to understand|easily understood|you sound unclear)\b", sentence) and not negated:
                result["pronunciation_claim"] = True
        if re.search(r"\b(?:your\s+)?(?:speech|voice|delivery|pronunciation)\b.{0,35}\b(?:clear|clearly|intelligible|understandable)\b", lower):
            result["unsupported_clarity_claim"] = True
    if re.search(r"\b(?:background\s+noise|noisy|noise\s+level)\b", lower):
        result["unsupported_noise_claim"] = True
    if re.search(r"\b(?:confiden(?:t|ce)|engaging|enthusias(?:m|tic)|anxi(?:ety|ous)|stressed|nervous)\b", lower):
        result["unsupported_personal_inference"] = True
    pace = data.get("words_per_minute")
    if pace is None and re.search(r"\b(pace|speed|speaking rate|words per minute|wpm|too fast|too slow)\b", lower):
        if not re.search(r"\b(unavailable|not available|cannot|can't|could not|not assessed|without|no transcript|not enough|insufficient|unable|too short|too quiet)\b", lower):
            result["unsupported_pace"] = True
    pauses = data.get("pause_count")
    if pauses is None and re.search(r"\b(pause[sd]?|hesitat\w*|long break)\b", lower):
        if not re.search(r"\b(unavailable|not available|cannot|can't|could not|not assessed|without|not enough|insufficient|unable)\b", lower):
            result["unsupported_pause"] = True
    if pauses == 0 and re.search(r"\b(?:your|the|that|these|long|several|many|multiple|frequent)\s+(?:long\s+|frequent\s+)?pauses\b", lower):
        if not re.search(r"\b(no|zero|not|without)\b.{0,20}\bpauses\b", lower):
            result["unsupported_pause"] = True
    # Only check explicit numerical values attached to a recognized WPM unit;
    # other numbers are intentionally left to manual review.
    units = re.findall(r"\b(\d+(?:\.\d+)?)\s*(?:wpm|words?\s*(?:per|/)\s*(?:minute|min))\b", lower)
    if units and (pace is None or any(abs(float(n) - float(pace)) > 1.1 for n in units)):
        result["wpm_number_mismatch"] = True
    pause_numbers = re.findall(r"\b(\d+)\s+(?:estimated\s+)?pauses?\b", lower)
    if pause_numbers and (pauses is None or any(int(n) != pauses for n in pause_numbers)):
        result["pause_number_mismatch"] = True
    result["unsupported_exam_score"] = bool(re.search(r"\b(?:ielts|toefl)\s+(?:band|score)\s*(?:of|is|:)?\s*\d", lower))
    recording = data.get("recording") or {}
    peak, clipped = recording.get("peak_dbfs"), recording.get("clipped_fraction")
    low_level_claim = re.search(r"\b(?:recorded level|recording level|recording volume|audio level|volume|recording)\s+(?:is|seems|appears)\s+(?:too\s+)?(?:low|quiet)\b", lower)
    if low_level_claim and ((not isinstance(peak, (int, float)) or peak >= -35) or
                            (isinstance(clipped, (int, float)) and clipped >= 0.01)):
        result["contradictory_low_level_advice"] = True
    clipping_claim = re.search(r"\b(?:shows|has|contains|exhibits|with)\s+(?:significant\s+|severe\s+|some\s+)?clipping\b|\b(?:audio|recording)\s+(?:is|was)\s+clipped\b", lower)
    clipping_negated = re.search(r"\b(?:no|not|without|no significant)\s+clipping\b", lower)
    if clipping_claim and not clipping_negated and (not isinstance(clipped, (int, float)) or clipped < 0.01):
        result["contradictory_clipping_claim"] = True
    return result


def quality_coverage(text: str, data: dict):
    """Review whether the response mentions simple recording-quality cues.

    -35 dBFS peak and 1% clipping are the prototype's heuristic rules, not
    universally established quality standards. Missing mentions are coverage
    indicators rather than proof that a complete answer is unsafe.
    """
    lower = text.lower()
    recording = data.get("recording") or {}
    peak, clipped = recording.get("peak_dbfs"), recording.get("clipped_fraction")
    clipping_present = isinstance(clipped, (int, float)) and clipped >= 0.01
    low_present = isinstance(peak, (int, float)) and peak < -35 and not clipping_present
    clipping_noted = bool(re.search(r"\bclipp\w*|\b(?:lower|reduce|reducing)\s+(?:the\s+)?(?:input\s+)?gain\b", lower))
    low_noted = bool(re.search(r"\bquiet\b|\blow\b.{0,25}\b(?:level|volume|peak)\b|\b(?:level|volume|peak)\b.{0,20}\blow\b|\bcloser\b", lower))
    return {"missed_clipping_cue": clipping_present and not clipping_noted,
            "missed_low_level_cue": low_present and not low_noted}


def summarize(records):
    flag_names = tuple(records[0]["flags"]) if records else ()
    counts = {name: sum(bool(row["flags"][name]) for row in records) for name in flag_names}
    coverage_names = tuple(records[0].get("quality_coverage", {})) if records else ()
    coverage_counts = {name: sum(bool(row.get("quality_coverage", {}).get(name)) for row in records) for name in coverage_names}
    return {"examples": len(records), "flagged_examples": sum(any(r["flags"].values()) for r in records),
            "flag_counts": counts, "quality_coverage_counts": coverage_counts,
            "scope": "Heuristic flags and cue coverage only; manually assess relevance, grounding and quality."}


def self_test():
    row = {"pronunciation_assessed": False, "words_per_minute": None, "pause_count": 0}
    assert assess("Your pronunciation is unclear.", row)["pronunciation_claim"]
    assert not assess("Pronunciation was not assessed.", row)["pronunciation_claim"]
    assert assess("You spoke at 140 words per minute.", row)["unsupported_pace"]
    assert assess("You spoke at 140 words per minute.", row)["wpm_number_mismatch"]
    assert not assess("You spoke at 140 words per minute.", {**row, "words_per_minute": 140.4})["wpm_number_mismatch"]
    assert assess("Your frequent pauses interrupt the flow.", row)["unsupported_pause"]
    print("Evaluator self-test passed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, help="Local base model directory")
    parser.add_argument("--adapter", type=Path, help="Local trained LoRA adapter directory")
    parser.add_argument("--test", type=Path, default=Path(__file__).parent / "data" / "test.jsonl")
    parser.add_argument("--output", type=Path, default=Path(__file__).parent / "evaluation.json")
    parser.add_argument("--limit", type=int, default=20, help="Number of held-out cases (0 = all)")
    parser.add_argument("--max-new-tokens", type=int, default=120)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--audit-existing", type=Path, help="Recheck saved generations without loading a model")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    if args.audit_existing:
        results = json.loads(args.audit_existing.read_text(encoding="utf-8"))
        for label in ("base", "adapter"):
            if label in results:
                records = results[label]["cases"]
                for record in records:
                    record["flags"] = assess(record["response"], record["input"])
                    record["quality_coverage"] = quality_coverage(record["response"], record["input"])
                results[label]["summary"] = summarize(records)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({k: v["summary"] for k, v in results.items() if isinstance(v, dict) and "summary" in v}, indent=2))
        return
    if not args.model or not args.model.is_dir():
        parser.error("--model must point to the downloaded local model directory")
    if args.adapter and not args.adapter.is_dir():
        parser.error("--adapter must point to a local adapter directory")
    if args.limit < 0 or args.max_new_tokens < 1:
        parser.error("--limit must be non-negative and --max-new-tokens positive")

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; load the intended CUDA-enabled Python environment.")
    rows = load_examples(args.test, args.limit)
    tokenizer = AutoTokenizer.from_pretrained(str(args.model), local_files_only=True)
    dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    quantization = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=dtype)
    model = AutoModelForCausalLM.from_pretrained(str(args.model), quantization_config=quantization,
                                                  torch_dtype=dtype, device_map={"": 0}, local_files_only=True)
    model.eval()

    def run(label):
        records = []
        for index, row in enumerate(rows):
            messages = [{"role": "system", "content": row["instruction"]},
                        {"role": "user", "content": json.dumps(row["input"], ensure_ascii=False, sort_keys=True)}]
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
            with torch.inference_mode():
                output = model.generate(**encoded, max_new_tokens=args.max_new_tokens, do_sample=False,
                                        pad_token_id=tokenizer.eos_token_id)
            text = tokenizer.decode(output[0, encoded["input_ids"].shape[1]:], skip_special_tokens=True).strip()
            record = {"index": index, "group": row.get("group"), "input": row["input"],
                      "reference": row.get("output"), "response": text, "flags": assess(text, row["input"]),
                      "quality_coverage": quality_coverage(text, row["input"])}
            records.append(record)
            print(f"[{label} {index + 1}/{len(rows)}] {text}", flush=True)
        return {"summary": summarize(records), "cases": records}

    results = {"evaluation_note": "Synthetic held-out cases; automated checks are incomplete and require human review.",
               "test_path": str(args.test), "base": run("base")}
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, str(args.adapter), is_trainable=False, local_files_only=True)
        model.eval()
        results["adapter"] = run("adapter")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v["summary"] for k, v in results.items() if isinstance(v, dict) and "summary" in v}, indent=2))
    print(f"Saved detailed results to {args.output}")


if __name__ == "__main__":
    main()
