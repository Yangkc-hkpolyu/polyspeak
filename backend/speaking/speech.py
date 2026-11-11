import base64
import io
from pathlib import Path
import wave
import httpx
import edge_tts

from .config import Settings
from .provider import ModelProvider, ProviderError


class SpeechService:
    def __init__(self, settings: Settings, provider: ModelProvider):
        self.settings = settings
        self.provider = provider

    async def transcribe(self, audio: bytes, language: str) -> str:
        if not self.settings.api_key:
            raise ProviderError("Speech recognition requires an Alibaba Cloud Model Studio API key. You can also type an answer.")
        if len(audio) > 5 * 1024 * 1024:
            raise ValueError("The recording is too long. Keep each answer within two minutes.")
        try:
            with wave.open(io.BytesIO(audio)) as wav:
                duration = wav.getnframes() / wav.getframerate()
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or not 0.3 <= duration <= 125:
                    raise ValueError("Upload a mono PCM WAV recording between 0.3 and 125 seconds long.")
        except (wave.Error, EOFError) as exc:
            raise ValueError("The recording could not be read. Please record it again.") from exc
        encoded = base64.b64encode(audio).decode("ascii")
        data = await self.provider.request({
            "model": self.settings.asr_model,
            "messages": [{"role": "user", "content": [{"type": "input_audio", "input_audio": {"data": f"data:audio/wav;base64,{encoded}"}}]}],
            "stream": False,
            "asr_options": {"language": language, "enable_itn": True},
        })
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("No clear speech was recognized. Record again or type your answer.")
        return content.strip()

    async def synthesize(self, text: str, language: str, target: Path) -> str:
        profile = self.settings.tts_profile(language)
        if profile["provider"] == "qwen":
            return await self.cloud_synthesize(text, language, target)
        try:
            await edge_tts.Communicate(text, profile["voice"], connect_timeout=15, receive_timeout=30).save(str(target))
            if target.exists() and target.stat().st_size > 100:
                return "EdgeTTS"
        except Exception as exc:
            raise ProviderError("The selected speech service is temporarily unavailable. Check your connection and retry.") from exc
        raise ProviderError("The selected speech service returned no audio.")

    async def cloud_synthesize(self, text: str, language: str, target: Path) -> str:
        base = self.settings.base_url.removesuffix("/compatible-mode/v1")
        url = f"{base}/api/v1/services/aigc/multimodal-generation/generation"
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(url, headers={"Authorization": f"Bearer {self.settings.api_key}"}, json={
                    "model": "qwen3-tts-flash",
                    "input": {"text": text, "voice": "Cherry", "language_type": "Chinese" if language == "zh" else "English"},
                })
                response.raise_for_status()
                audio_url = response.json()["output"]["audio"]["url"]
                audio = await client.get(audio_url)
                audio.raise_for_status()
                target.write_bytes(audio.content)
            return "Qwen3-TTS-Flash"
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError("Speech synthesis failed. Select Replay to try again shortly.") from exc

