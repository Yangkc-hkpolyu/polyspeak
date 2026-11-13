"""Measure saved PCM audio; energy activity is an estimate, not pronunciation."""
import re
import wave

import numpy as np

from .worker import normalize_metrics


def measure_recording(path, transcript):
    with wave.open(str(path)) as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
            raise ValueError("Unsupported recording format")
        if not 0 < wav.getnframes() <= 16000 * 180:
            raise ValueError("Unsupported recording length")
        pcm = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float64)
    samples = pcm / 32768.0
    peak = float(np.max(np.abs(samples)))
    metrics = {"status": "insufficient_audio", "detection_method": "energy_estimate",
               "speaking_span_seconds": None, "transcript_word_count": None,
               "words_per_minute": None, "pause_count": None, "pauses": [],
               "recording": {"peak_dbfs": max(-160.0, 20 * np.log10(peak)) if peak else -160.0,
                             "clipped_fraction": float(np.mean(np.abs(pcm) >= 32767))}}
    # Twenty-millisecond frames; quiet gaps inside the detected span only.
    frames = np.pad(samples, (0, (-len(samples)) % 320)).reshape(-1, 320)
    rms = np.sqrt(np.mean(frames * frames, axis=1))
    threshold = max(0.001, float(np.percentile(rms, 90)) * 0.12)
    active = np.flatnonzero(rms >= threshold)
    if len(active) < 10:
        return normalize_metrics(metrics)
    first, last = int(active[0]), int(active[-1])
    span = round((last - first + 1) * .02, 3)
    pauses, start = [], None
    for index in range(first, last + 1):
        if rms[index] < threshold:
            start = index if start is None else start
        elif start is not None:
            if index - start >= 30:
                pauses.append({"start_seconds": round(start * .02, 3),
                               "end_seconds": round(index * .02, 3),
                               "duration_seconds": round((index - start) * .02, 3)})
            start = None
    count = len(re.findall(r"\b[A-Za-z]+(?:['’-][A-Za-z]+)*\b", transcript or "")) or None
    wpm = round(count * 60 / span, 3) if count else None
    # Implausible ASR alignment must remain unavailable, never clipped to a plausible value.
    if wpm is not None and (wpm > 1000 or count > 3000):
        count, wpm = None, None
    metrics.update(status="ok", speaking_span_seconds=span, transcript_word_count=count,
                   words_per_minute=wpm, pause_count=len(pauses), pauses=pauses)
    return normalize_metrics(metrics)
