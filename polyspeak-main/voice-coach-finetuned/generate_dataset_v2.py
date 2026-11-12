"""Synthetic v2 coverage data; influenced by the first round's evaluation."""
import json
import random
from collections import Counter
from pathlib import Path

from generate_dataset import INSTRUCTION, INSUFFICIENT, choose, make_case

ROOT = Path(__file__).resolve().parent / "data_v2"
SPLIT_SEEDS = {"train": 443102, "validation": 443103, "test": 443104}


def canonical_input(row):
    return json.dumps(row["input"], sort_keys=True, ensure_ascii=False)


def make_insufficient(split, number, rng):
    # Samples may be quiet, too short or otherwise not detected as speech;
    # a transcript can exist even though the recording has no measurable span.
    metrics = {"status": "insufficient_audio", "detection_method": rng.choice(("silero_vad", "energy_estimate")),
        "speaking_span_seconds": None, "transcript_word_count": rng.choice((None, rng.randint(1, 30))),
        "words_per_minute": None, "pause_count": None, "pauses": [],
        "recording": {"peak_dbfs": round(rng.uniform(-90.0, -20.0), 2), "clipped_fraction": 0.0},
        "pronunciation_assessed": False}
    return {"instruction": INSTRUCTION, "input": metrics, "output": choose(INSUFFICIENT, split, rng),
            "group": "insufficient-audio", "id": f"v2-{split}-insufficient-{number:03d}"}


def main():
    ROOT.mkdir(parents=True, exist_ok=True)
    observed = set()
    distributions = {}
    for split, seed in SPLIT_SEEDS.items():
        rng = random.Random(seed)
        rows = []
        per_combination = 32 if split == "train" else 5
        insufficient = 32 if split == "train" else 18
        for transcript in (False, True):
            for quality in ("low", "normal", "clip"):
                for pauses in ("zero", "one", "many"):
                    group = (transcript, quality, pauses)
                    for _ in range(per_combination):
                        for attempt in range(100):
                            row = make_case(split, group, len(rows), rng)
                            row["id"] = 'v2-' + row['id']
                            key = canonical_input(row)
                            if key not in observed:
                                break
                        else:
                            raise RuntimeError("Cannot generate a unique input")
                        observed.add(key)
                        rows.append(row)
        for _ in range(insufficient):
            for attempt in range(100):
                row = make_insufficient(split, len(rows), rng)
                key = canonical_input(row)
                if key not in observed:
                    break
            else:
                raise RuntimeError("Cannot generate a unique insufficient-audio input")
            observed.add(key)
            rows.append(row)
        rng.shuffle(rows)
        (ROOT / f"{split}.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        distributions[split] = {"rows": len(rows), "combinations": len({r['group'] for r in rows if r['input']['status'] == 'ok'}),
          "detection_methods": dict(Counter(r['input']['detection_method'] for r in rows)),
          "statuses": dict(Counter(r['input']['status'] for r in rows))}
    print(json.dumps(distributions, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
