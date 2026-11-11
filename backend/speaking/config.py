from dataclasses import dataclass
import os
from pathlib import Path
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    api_key: str = ""
    base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    chat_model: str = "qwen-plus-latest"
    asr_model: str = "qwen3-asr-flash"
    realtime_asr_model: str = "qwen3-asr-flash-realtime"
    realtime_tts_model: str = "qwen3-tts-flash-realtime"
    realtime_url: str = ""
    port: int = 8008
    runtime: Path = ROOT / "speaking-runtime"
    model_path: Path = ROOT / "speaking-models/wav2lip.pth"
    portrait: Path = ROOT / "backend/speaking/assets/nora.png"
    avatar_directory: Path = ROOT / "speaking-models/avatars/nora"
    avatar_device: str = "auto"
    avatar_fps: int = 25
    avatar_batch_size: int = 4
    torch_threads: int = 4
    voice_en: str = "en-US-JennyNeural"
    voice_zh: str = "zh-CN-XiaoxiaoNeural"
    tts_provider: str = "edgetts"
    azure_key: str = ""
    azure_region: str = "eastus"

    def tts_profile(self, language="en"):
        if language not in ("en", "zh"):
            raise ValueError("Unsupported speech language.")
        if self.tts_provider == "edgetts":
            voice = self.voice_en if language == "en" else self.voice_zh
            if not voice.startswith(language + "-"):
                raise ValueError("The configured speech voice does not match the requested language.")
            return {"provider": "edgetts", "model": "EdgeTTS", "voice": voice, "language": language}
        if self.tts_provider == "qwen":
            return {"provider": "qwen", "model": self.realtime_tts_model,
                    "voice": "Cherry", "language": language}
        raise ValueError("SPEAKING_TTS_PROVIDER must be edgetts or qwen.")


def load_settings():
    # This is the PRIVATE copied configuration on E:, never the C: original.
    copied = {k: v for k, v in dotenv_values(ROOT / "backend/.env").items() if v is not None}
    local = {k: v for k, v in dotenv_values(ROOT / "speaking.env").items() if v is not None}
    values = {**copied, **local, **os.environ}
    return Settings(
        api_key=values.get("DASHSCOPE_API_KEY", "").strip(),
        base_url=values.get("SPEAKING_MODEL_BASE_URL", Settings.base_url).rstrip("/"),
        chat_model=values.get("SPEAKING_CHAT_MODEL", Settings.chat_model),
        asr_model=values.get("SPEAKING_ASR_MODEL", Settings.asr_model),
        realtime_asr_model=values.get("SPEAKING_REALTIME_ASR_MODEL", Settings.realtime_asr_model),
        realtime_tts_model=values.get("SPEAKING_REALTIME_TTS_MODEL", Settings.realtime_tts_model),
        realtime_url=values.get("SPEAKING_REALTIME_URL", ""),
        port=int(values.get("SPEAKING_PORT", "8008")),
        avatar_device=values.get("SPEAKING_AVATAR_DEVICE", "auto"),
        avatar_directory=Path(values.get("SPEAKING_AVATAR_DIR", str(Settings.avatar_directory))),
        tts_provider=values.get("SPEAKING_TTS_PROVIDER", Settings.tts_provider).strip().lower(),
        voice_en=values.get("SPEAKING_VOICE_EN", Settings.voice_en).strip(),
        voice_zh=values.get("SPEAKING_VOICE_ZH", Settings.voice_zh).strip(),
        azure_key=values.get("AZURE_SPEECH_KEY", "").strip() or values.get("AZURE_KEY", "").strip(),
        azure_region=values.get("AZURE_REGION", "eastus"),
    )
