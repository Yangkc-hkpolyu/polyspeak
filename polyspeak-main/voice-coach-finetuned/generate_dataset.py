"""Generate reproducible synthetic, evidence-limited voice coaching examples."""
import json
import random
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "data"
INSTRUCTION = (
    "You are a supportive English-speaking practice coach. Use only the provided measurements. "
    "Write brief, practical feedback in two or three sentences. Treat pace, pauses, and recording "
    "quality as estimates, not exam scores. Do not assess pronunciation, accent, or intelligibility. "
    "Never invent missing data or claim a speaker made a mistake."
)

PACE = {
    "train": ["The estimated pace is {wpm} words per minute over {span} seconds.",
              "Your estimated pace was {wpm} words per minute across a {span}-second speaking span.",
              "The recording suggests about {wpm} words per minute over {span} seconds."],
    "validation": ["Across the estimated {span}-second speaking span, the pace was {wpm} words per minute."],
    "test": ["For the estimated {span} seconds of speaking, the rate is about {wpm} words per minute."],
}
NO_PACE = {
    "train": ["A pace estimate is unavailable without a transcript.",
              "The words-per-minute estimate is unavailable because no transcript was supplied."],
    "validation": ["Without transcript text, this check cannot estimate words per minute."],
    "test": ["There is no transcript to use for a pace estimate."],
}
PAUSES = {
    "train": ["Replay the {count} estimated pause{suffix}; decide whether {phrase} your phrasing.",
              "Listen back to the {count} estimated pause{suffix} and consider whether {feels} natural."],
    "validation": ["The check found {count} estimated pause{suffix}; replay and consider how {pronoun} sound in context."],
    "test": ["Try replaying the {count} estimated pause{suffix} to see whether {phrase} your phrasing."],
}
ZERO = {
    "train": ["No pauses of at least 0.6 seconds were detected; replay the recording to check the rhythm.",
              "No longer pauses were detected; you can replay the answer and compare the rhythm with another attempt."],
    "validation": ["No pauses of at least 0.6 seconds were detected; listen back to check the flow."],
    "test": ["The check found no pauses of at least 0.6 seconds; replay the answer to review its rhythm."],
}
CLIP = {
    "train": ["The recording shows clipping; try lowering the input gain or moving the microphone farther away."],
    "validation": ["Some samples are clipped; try reducing microphone gain before recording again."],
    "test": ["Clipping was detected in the recording; try moving back from the microphone or lowering its gain."],
}
LOW = {
    "train": ["The recorded level is low; try moving the microphone closer or checking input gain."],
    "validation": ["The recording level is low; check the microphone position or volume."],
    "test": ["The recording peak is low; try checking the microphone and its input level."],
}
INSUFFICIENT = {
    "train": ["There is not enough detected audio to estimate pace or pauses. Check your microphone and try a longer recording.",
              "The audio was too short or quiet to estimate speaking pace. Check the microphone and record a longer answer."],
    "validation": ["This recording has insufficient detected audio for a pace estimate. Check the microphone before trying again."],
    "test": ["There is insufficient detected audio to estimate pace or pauses. Try recording a longer response after checking the microphone."],
}

# Hold out entire combinations of transcript availability, recording state, and
# pause bucket. Template sets also do not cross splits. Each component is seen
# in training, but some combinations never are.
HELD_OUT_TEST = {(False, "clip", "many"), (True, "low", "zero"), (True, "normal", "many")}
HELD_OUT_VALID = {(False, "low", "one"), (True, "clip", "zero"), (False, "normal", "many")}


def choose(table, split, rng):
    return rng.choice(table[split])


def make_case(split, group, number, rng):
    has_text, quality, pause_bucket = group
    span = round(rng.uniform(12.0, 40.0), 1)
    count = rng.randint(18, 85) if has_text else None
    wpm = round(count * 60 / span, 1) if count is not None else None
    pause_count = {"zero": 0, "one": 1, "many": rng.randint(2, 4)}[pause_bucket]
    pauses = []
    for n in range(pause_count):
        start = round((n + 1) * span / (pause_count + 1), 1)
        duration = round(rng.uniform(0.6, 1.4), 1)
        pauses.append({"start_seconds": start, "end_seconds": round(start + duration, 1), "duration_seconds": duration})
    if quality == "low":
        peak, clipped = round(rng.uniform(-51, -36), 1), 0.0
    elif quality == "clip":
        peak, clipped = 0.0, round(rng.uniform(0.012, 0.08), 4)
    else:
        peak, clipped = round(rng.uniform(-28, -4), 1), 0.0
    metrics = {"status": "ok", "detection_method": rng.choice(("silero_vad", "energy_estimate")), "speaking_span_seconds": span,
               "transcript_word_count": count, "words_per_minute": wpm, "pause_count": pause_count,
               "pauses": pauses, "recording": {"peak_dbfs": peak, "clipped_fraction": clipped},
               "pronunciation_assessed": False}
    if has_text:
        first = choose(PACE, split, rng).format(wpm=wpm, span=span)
    else:
        first = choose(NO_PACE, split, rng)
    if pause_count:
        last = choose(PAUSES, split, rng).format(count=pause_count, suffix="" if pause_count == 1 else "s", pronoun="it" if pause_count == 1 else "they", phrase="it fits" if pause_count == 1 else "they fit", feels="it feels" if pause_count == 1 else "they feel")
    else:
        last = choose(ZERO, split, rng)
    advice = [first, last]
    if quality == "low":
        advice.append(choose(LOW, split, rng))
    elif quality == "clip":
        advice.append(choose(CLIP, split, rng))
    return {"instruction": INSTRUCTION, "input": metrics, "output": " ".join(advice),
            "group": f"{int(has_text)}-{quality}-{pause_bucket}", "id": f"{split}-{number:04d}"}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    rng = random.Random(4431)
    buckets = {name: [] for name in ("train", "validation", "test")}
    for has_text in (False, True):
        for quality in ("low", "normal", "clip"):
            for pauses in ("zero", "one", "many"):
                group = (has_text, quality, pauses)
                split = "test" if group in HELD_OUT_TEST else "validation" if group in HELD_OUT_VALID else "train"
                for _ in range(32):
                    buckets[split].append(make_case(split, group, len(buckets[split]), rng))
    for split, bucket in buckets.items():
        for index in range(32):
            inp = {"status": "insufficient_audio", "detection_method": rng.choice(("silero_vad", "energy_estimate")), "speaking_span_seconds": None,
                   "transcript_word_count": rng.choice((None, 14)), "words_per_minute": None, "pause_count": None, "pauses": [],
                   "recording": {"peak_dbfs": round(-60.0 - index - {"train": 0.0, "validation": 0.2, "test": 0.4}[split], 1), "clipped_fraction": 0.0}, "pronunciation_assessed": False}
            bucket.append({"instruction": INSTRUCTION, "input": inp, "output": choose(INSUFFICIENT, split, rng),
                           "group": "insufficient-" + split, "id": f"{split}-insufficient-{index:02d}"})
        rng.shuffle(bucket)
        (ROOT / f"{split}.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in bucket), encoding="utf-8")
    groups = {name: {row["group"] for row in rows} for name, rows in buckets.items()}
    assert not groups['train'] & groups['validation'] and not groups['train'] & groups['test'] and not groups['validation'] & groups['test']
    for split, rows in buckets.items():
        assert all(row['input']['pronunciation_assessed'] is False for row in rows)
        assert all(len(row['output']) < 600 for row in rows)
        print(split, 'rows=',len(rows),'groups=',len(groups[split]),'statuses=',dict(Counter(r['input']['status'] for r in rows)))


if __name__ == '__main__':
    main()
