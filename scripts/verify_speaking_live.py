"""Create a SYNTHETIC microphone fixture and verify the configured speech service."""
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import imageio_ffmpeg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.speaking.config import load_settings
from backend.speaking.provider import ModelProvider
from backend.speaking.speech import SpeechService


async def main():
    folder = ROOT / "speaking-runtime/qa"
    folder.mkdir(exist_ok=True)
    settings = load_settings()
    provider = ModelProvider(settings)
    speech = SpeechService(settings, provider)
    text = "I learned to bake bread from my aunt. We practised together every weekend, and I enjoyed sharing the bread with my friends."
    audio = folder / "synthetic-input.audio"
    tts_provider = await speech.synthesize(text, "en", audio)
    target = folder / "synthetic-input.wav"
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(audio), "-ar", "16000", "-ac", "1", str(target)], check=True)
    recognized = await speech.transcribe(target.read_bytes(), "en")
    assert "bread" in recognized.lower(), recognized
    result = {"synthetic_audio": True, "input": text, "recognized": recognized, "tts": tts_provider, "asr": settings.asr_model}
    (folder / "speech-results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print("SYNTHETIC_TTS_ASR_PASSED", json.dumps(result))


if __name__ == "__main__":
    asyncio.run(main())
