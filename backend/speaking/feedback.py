from difflib import SequenceMatcher
import math
import re
from .provider import ProviderError

DIMENSIONS = ("coherence", "vocabulary", "grammar", "task_response")


def english_feedback_text(value, limit):
    """Validate generated commentary; evidence quotes and transcripts bypass this."""
    text = str(value)
    if re.search(r"[\u3400-\u9fff\uf900-\ufaff]", text):
        raise ProviderError("The model did not return feedback in English. Your answers are saved. Please retry feedback.")
    return text[:limit]


def concise_explanation(value):
    """Show concise English coaching advice, not generated life stories."""
    if not isinstance(value, str) or not value.strip() or re.search(r"[\u3400-\u9fff\uf900-\ufaff]", value):
        return None
    words = lambda text: re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", text)
    if len(value) > 1800 or len(words(value)) > 80:
        return None
    # Short quoted language examples are allowed. The surrounding advice must
    # remain an explanation rather than a first-person replacement answer.
    quoted = re.compile(r'"[^"\n]*"|“[^”\n]*”|(?<!\w)\x27[^\x27\n]*\x27(?!\w)|‘[^’\n]*’')
    if any(len(words(match.group())) > 12 for match in quoted.finditer(value)):
        return None
    explanation = quoted.sub("", value)
    if len(words(explanation)) < 2 or re.search(r"\b(?:I|me|my|mine|we|us|our|ours)\b", explanation, re.I):
        return None
    return value.strip()


def repetition_check(target, transcript):
    tokens = lambda value: re.findall(r"[a-z]+(?:'[a-z]+)?", value.lower())
    expected, actual = tokens(target), tokens(transcript)
    differences = []
    for kind, a, b, c, d in SequenceMatcher(None, expected, actual, autojunk=False).get_opcodes():
        if kind != "equal":
            differences.append({"type": kind, "expected": " ".join(expected[a:b]), "recognized": " ".join(actual[c:d])})
    return {"target": target, "recognized": transcript, "differences": differences, "scope": "This compares words in the target sentence and speech transcript only. It cannot determine pronunciation accuracy."}


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
                dimensions.append({"key": key, "score": round(score, 1), "comment": english_feedback_text(item.get("comment", ""), 1500)})
            except (TypeError, ValueError, KeyError):
                pass
    if execution == "live" and len(dimensions) != 4:
        raise ProviderError("The feedback response is incomplete. Your answers are saved. Please generate feedback again.")
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
        return [english_feedback_text(x, 1800) for x in value[:5] if isinstance(x, str)] if isinstance(value, list) else []
    return {"source": "live_model" if execution == "live" else "offline_demo", "summary": english_feedback_text(raw.get("summary", ""), 2400), "dimensions": dimensions, "overall_score": None, "strengths": strings("strengths"), "improvements": strings("improvements"), "next_steps": strings("next_steps"), "examples": examples, "scope": "The four scores are text-based practice metrics (0–10), not IELTS bands or TOEFL scores. Pronunciation, speaking speed, pauses, and prosody require a separate audio assessment and are not scored when it is unavailable."}
