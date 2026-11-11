from difflib import SequenceMatcher
import math
import re
from .provider import ProviderError

DIMENSIONS = ("coherence", "vocabulary", "grammar", "task_response")


def concise_explanation(value):
    """Show Chinese advice with short language examples, not generated life stories."""
    if not isinstance(value, str) or not re.search(r"[\u4e00-\u9fff]", value):
        return None
    for segment in re.split(r"[\u4e00-\u9fff]", value):
        if len(re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", segment)) > 12:
            return None
    return value[:1800]


def repetition_check(target, transcript):
    tokens = lambda value: re.findall(r"[a-z]+(?:'[a-z]+)?", value.lower())
    expected, actual = tokens(target), tokens(transcript)
    differences = []
    for kind, a, b, c, d in SequenceMatcher(None, expected, actual, autojunk=False).get_opcodes():
        if kind != "equal":
            differences.append({"type": kind, "expected": " ".join(expected[a:b]), "recognized": " ".join(actual[c:d])})
    return {"target": target, "recognized": transcript, "differences": differences, "scope": "Only wording in the original and ASR transcript is compared; this cannot establish pronunciation accuracy."}


def normalize_feedback(raw, turns, execution):
    dimensions = []
    items = raw.get("dimensions", [])
    for key in DIMENSIONS:
        item = next((x for x in items if isinstance(x, dict) and x.get("key") == key), None) if isinstance(items, list) else None
        if item:
            try:
                score = float(item["score"])
                if not math.isfinite(score) or not 0 <= score <= 10:
                    continue
                dimensions.append({"key": key, "score": round(score, 1), "comment": str(item.get("comment", ""))[:1500]})
            except (TypeError, ValueError, KeyError):
                pass
    if execution == "live" and len(dimensions) != 4:
        raise ProviderError("Feedback was incomplete. Your answers are saved; retry generation.")
    if execution == "demo":
        dimensions = []
    valid = {x["id"]: x["answer"] for x in turns if not x.get("skipped") and x.get("transcript_available", True)}
    examples = []
    raw_examples = raw.get("examples", [])
    for item in (raw_examples[:5] if isinstance(raw_examples, list) else []):
        if not isinstance(item, dict):
            continue
        if not isinstance(item.get("turn_id"), str):
            continue
        quote = str(item.get("quote", "")).strip()
        suggestion = concise_explanation(item.get("suggestion"))
        if suggestion and quote and quote in valid.get(item.get("turn_id"), ""):
            # Do not expose free-form autobiographical rewrites: they can add facts
            # even when a prompt asks the model to preserve the learner's meaning.
            examples.append({"turn_id": item["turn_id"], "quote": quote, "suggestion": suggestion})
    def strings(key):
        value = raw.get(key, [])
        return [x[:1800] for x in value[:5] if isinstance(x, str)] if isinstance(value, list) else []
    return {"source": "live_model" if execution == "live" else "offline_demo", "summary": str(raw.get("summary", ""))[:2400], "dimensions": dimensions, "overall_score": None, "strengths": strings("strengths"), "improvements": strings("improvements"), "next_steps": strings("next_steps"), "examples": examples, "scope": "The four scores are text-based practice metrics (0–10), not IELTS bands or TOEFL scores. Pronunciation, speed, pauses and prosody are assessed only with independent audio; they remain unscored when unavailable."}
