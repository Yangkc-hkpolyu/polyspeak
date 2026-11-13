"""Offline LoRA advice worker. Accept structured metrics only, never audio/text.

The output filter is deliberately conservative and is not a proof of factual
correctness. Rejected or unavailable models never return substitute advice.
"""
from __future__ import annotations

import argparse
import contextlib
import json
import math
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent
if os.environ.get("VOICE_COACH_DEPS"):
    sys.path.insert(0, os.environ["VOICE_COACH_DEPS"])
INSTRUCTION = ("You are a supportive English-speaking practice coach. Use only the provided measurements. "
               "Write brief, practical feedback in two or three sentences. Treat pace, pauses, and recording quality "
               "as estimates, not exam scores. Do not assess pronunciation, accent, or intelligibility. "
               "Never invent missing data or claim a speaker made a mistake.")


def _number(value, lower, upper, integer=False):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("invalid metric")
    if not lower <= value <= upper or (integer and int(value) != value):
        raise ValueError("metric outside range")
    return int(value) if integer else round(float(value), 3)


def normalize_metrics(source):
    """Whitelist only known numeric measurement fields; omit audio and transcript."""
    if not isinstance(source, dict):
        raise ValueError("metrics must be an object")
    status = source.get("status")
    if status not in ("ok", "insufficient_audio"):
        raise ValueError("invalid status")
    method = source.get("detection_method")
    if method not in ("energy_estimate", "silero_vad"):
        raise ValueError("invalid detection method")
    recording = source.get("recording")
    if not isinstance(recording, dict):
        raise ValueError("invalid recording metrics")
    spans = source.get("pauses", [])
    if not isinstance(spans, list) or len(spans) > 300:
        raise ValueError("invalid pause list")
    pauses = []
    for span in spans:
        if not isinstance(span, dict):
            raise ValueError("invalid pause")
        start = _number(span.get("start_seconds"), 0, 180)
        end = _number(span.get("end_seconds"), 0, 180)
        duration = _number(span.get("duration_seconds"), 0, 180)
        if start is None or end is None or duration is None or start > end or abs(end-start-duration) > 0.05:
            raise ValueError("invalid pause times")
        pauses.append({"start_seconds": start, "end_seconds": end, "duration_seconds": duration})
    span_seconds = _number(source.get("speaking_span_seconds"), 0, 180)
    count = _number(source.get("transcript_word_count"), 0, 3000, True)
    wpm = _number(source.get("words_per_minute"), 0, 1000)
    pause_count = _number(source.get("pause_count"), 0, 300, True)
    if pause_count is not None and pause_count != len(pauses):
        raise ValueError("pause count mismatch")
    if status != "ok" and any(v is not None for v in (span_seconds, wpm, pause_count)):
        raise ValueError("unavailable metrics must not be provided")
    if wpm is not None and (not span_seconds or count is None or abs(wpm - count * 60 / span_seconds) > 2):
        raise ValueError("pace inconsistent with count and duration")
    return {"status": status, "detection_method": method, "speaking_span_seconds": span_seconds,
            "transcript_word_count": count, "words_per_minute": wpm,
            "pause_count": pause_count, "pauses": pauses,
            "recording": {"peak_dbfs": _number(recording.get("peak_dbfs"), -160, 6),
                          "clipped_fraction": _number(recording.get("clipped_fraction"), 0, 1)},
            "pronunciation_assessed": False}


_FORBIDDEN = re.compile(r"\b(pronounc\w*|pronuncia\w*|mispronounc\w*|mispronuncia\w*|accent\w*|articulat\w*|intelligib\w*|unintelligib\w*|understandab\w*|(?:un)?clear(?:ly|ness)?|ielts|toefl|band|score\w*|grade\w*|fluen\w*|hesitat\w*|mistake\w*|wrong|error\w*|noise|noisy)\b", re.I)
_NUMBER = re.compile(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])")
_PACE_NUMBER = re.compile(r"\b(\d+(?:\.\d+)?)\s*(?:wpm|words?\s*(?:per|/)\s*(?:minute|min))\b", re.I)
_PAUSE_NUMBER = re.compile(r"\b(\d+)\s+(?:estimated\s+)?pauses?\b", re.I)
_SPAN_NUMBER = re.compile(r"\b(?:over|across|during)\s+(?:a\s+)?(\d+(?:\.\d+)?)(?:\s*-\s*second\s+speaking\s+span|\s+seconds?(?:\s+speaking\s+span)?)\b", re.I)
_PAUSE_THRESHOLD = re.compile(r"\bno\s+pauses?\s+of\s+at\s+least\s+0\.6\s+seconds?\b", re.I)
_UNAVAILABLE = re.compile(r"\b(?:unavailable|not available|not assessed|not measured|cannot|can't|could not|without|no transcript|not enough|insufficient|unable|too short)\b", re.I)
_LOUDER_SUGGESTION = re.compile(r"\b(?:mov(?:e|ing)|bring(?:ing)?|plac(?:e|ing)|position(?:ing)?|put(?:ting)?|hold(?:ing)?)\b.{0,40}\b(?:microphone|mic)\b.{0,25}\b(?:closer|nearer)\b|\b(?:closer|nearer)\b.{0,30}\b(?:microphone|mic)\b|\b(?:increase|increasing|raise|raising|turn up|turning up|boost|boosting)\b.{0,35}\b(?:gain|volume|level)\b", re.I)
_QUIETER_SUGGESTION = re.compile(r"\b(?:mov(?:e|ing)|bring(?:ing)?|plac(?:e|ing)|position(?:ing)?|put(?:ting)?|hold(?:ing)?)\b.{0,40}\b(?:microphone|mic)\b.{0,25}\b(?:farther|further|away)\b|\b(?:farther|further)\b.{0,30}\b(?:microphone|mic)\b|\b(?:reduce|reducing|lower|lowering|turn down|turning down|decrease|decreasing)\b.{0,35}\b(?:gain|volume|level)\b", re.I)


def validate_output(text, metrics):
    """Return whether a generated answer passes conservative grounding checks.

    This is a lexical filter, not a clinical or factuality guarantee.
    """
    if not isinstance(text, str) or not text.strip() or len(text) > 420 or _FORBIDDEN.search(text):
        return False
    if re.search(r"[\r\n]|https?://|\b(?:too fast|too slow|perfect|excellent|poor|bad)\b", text, re.I):
        return False
    stripped = text
    for pattern, field in ((_PACE_NUMBER, "words_per_minute"), (_PAUSE_NUMBER, "pause_count"), (_SPAN_NUMBER, "speaking_span_seconds")):
        for match in pattern.finditer(text):
            metric = metrics[field]
            if metric is None or abs(float(match.group(1)) - float(metric)) > 0.1:
                return False
        stripped = pattern.sub("", stripped)
    # Voice-coach uses a documented 0.6-second threshold for pause counting.
    if _PAUSE_THRESHOLD.search(stripped):
        if metrics["pause_count"] != 0:
            return False
        stripped = _PAUSE_THRESHOLD.sub("", stripped)
    if _NUMBER.search(stripped):
        return False
    # Spellings such as "three pauses" must not bypass numerical checks.
    if re.search(r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|hundred)\b", text, re.I):
        return False
    peak, clipping = metrics["recording"]["peak_dbfs"], metrics["recording"]["clipped_fraction"]
    if _LOUDER_SUGGESTION.search(text) and (peak is None or peak >= -35 or clipping is None or clipping >= 0.01):
        return False
    if _QUIETER_SUGGESTION.search(text) and (clipping is None or clipping < 0.01):
        return False
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if metrics["words_per_minute"] is None and re.search(r"\b(?:pace|speed|rate|wpm|fast|slow|quickly|slowly)\b", sentence, re.I) and not _UNAVAILABLE.search(sentence):
            return False
        if metrics["pause_count"] is None and re.search(r"\b(?:pause|pauses|break|breaks)\b", sentence, re.I) and not _UNAVAILABLE.search(sentence):
            return False
        if metrics["pause_count"] == 0 and re.search(r"\b(?:a|an|your|the|those|long|several|many)\s+(?:estimated\s+)?pauses?\b", sentence, re.I) and not re.search(r"\b(?:no|zero|without)\b", sentence, re.I):
            return False
        if re.search(r"\b(?:clipp\w*|distort\w*)\b", sentence, re.I):
            if metrics["recording"]["clipped_fraction"] is None or metrics["recording"]["clipped_fraction"] < 0.01:
                return False
        if re.search(r"\bpeak\w*\b", sentence, re.I) and metrics["recording"]["peak_dbfs"] is None:
            return False
        if re.search(r"\b(?:quiet|low volume|low level|too soft|inaudible|(?:recorded\s+|recording\s+|audio\s+|input\s+|peak\s+|signal\s+)?(?:level|volume)\s+(?:is|was|appears|seems)\s+(?:(?:very|too|quite|slightly)\s+)?low)\b", sentence, re.I):
            if metrics["recording"]["peak_dbfs"] is None or metrics["recording"]["peak_dbfs"] >= -35:
                return False
        if metrics["recording"]["peak_dbfs"] is None and re.search(r"\b(?:volume|loud|soft|quiet)\b", sentence, re.I):
            return False
    return True


def rejection_category(text, metrics):
    """Classify a rejection without returning the generated text or inputs."""
    if not isinstance(text, str) or not text.strip() or len(text) > 420:
        return "output_empty_or_too_long"
    if _FORBIDDEN.search(text):
        return "output_unverified_claim"
    remaining = text
    for pattern in (_PACE_NUMBER, _PAUSE_NUMBER, _SPAN_NUMBER, _PAUSE_THRESHOLD):
        remaining = pattern.sub("", remaining)
    if _NUMBER.search(remaining) or re.search(r"\b(?:zero|one|two|three|four|five|six|seven|eight|nine|ten|hundred)\b", text, re.I):
        return "output_unverified_number"
    return "output_failed_grounding_checks"


def generate_advice(source, base_path=None, adapter_path=None):
    """Generate from local base + adapter on CPU, leaving avatar GPU work alone."""
    def failure(status, reason):
        return {"status": status, "advice": None, "reason": reason, "model": "local_lora"}
    try:
        metrics = normalize_metrics(source)
    except (ValueError, TypeError):
        return failure("rejected", "invalid_metrics")
    base = Path(base_path or ROOT / "base").resolve()
    adapter = Path(adapter_path or ROOT / "adapter").resolve()
    if not (base / "model.safetensors").is_file() or not (adapter / "adapter_model.safetensors").is_file():
        return failure("unavailable", "local_model_missing")
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    model = None
    torch = None
    try:
        # Third-party loader progress belongs on stderr, never the JSON response.
        with contextlib.redirect_stdout(sys.stderr):
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer
            torch.set_num_threads(2)
            tokenizer = AutoTokenizer.from_pretrained(str(base), local_files_only=True)
            model = AutoModelForCausalLM.from_pretrained(str(base), torch_dtype=torch.float16, device_map={"": "cpu"}, local_files_only=True, use_safetensors=True)
            # PEFT otherwise defaults to an automatic second dispatch, which can
            # unexpectedly request disk offload on machines with limited free RAM.
            model = PeftModel.from_pretrained(model, str(adapter), is_trainable=False,
                                             device_map={"": "cpu"}, local_files_only=True)
            model.eval()
            messages = [{"role": "system", "content": INSTRUCTION},
                        {"role": "user", "content": json.dumps(metrics, ensure_ascii=False, sort_keys=True)}]
            prompt = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
            inputs = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(model.device)
            with torch.inference_mode():
                output = model.generate(**inputs, max_new_tokens=110, do_sample=False, pad_token_id=tokenizer.eos_token_id)
            answer = tokenizer.decode(output[0, inputs["input_ids"].shape[1]:], skip_special_tokens=True).strip()
        if not validate_output(answer, metrics):
            return failure("rejected", rejection_category(answer, metrics))
        return {"status": "ok", "advice": answer, "reason": None, "model": "local_lora"}
    except Exception as exc:
        # Never return exception text, which can contain paths or user data.
        oom = torch is not None and isinstance(exc, torch.cuda.OutOfMemoryError)
        return failure("unavailable", "gpu_memory_exhausted" if oom else "model_load_or_inference_failed")
    finally:
        del model
        if torch is not None and torch.cuda.is_available():
            torch.cuda.empty_cache()


def main():
    parser = argparse.ArgumentParser(description="Local offline advice worker")
    parser.add_argument("--base", type=Path, default=ROOT / "base")
    parser.add_argument("--adapter", type=Path, default=ROOT / "adapter")
    args = parser.parse_args()
    try:
        raw = sys.stdin.read(65537)
        if len(raw) > 65536:
            raise ValueError("input too large")
        result = generate_advice(json.loads(raw), args.base, args.adapter)
    except (ValueError, TypeError, json.JSONDecodeError):
        result = {"status": "rejected", "advice": None, "reason": "invalid_input", "model": "local_lora"}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
