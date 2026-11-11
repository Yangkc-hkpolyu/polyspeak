"""Return bounded, complete TTS audio without loading the video avatar model."""
from contextlib import aclosing
from io import BytesIO
import wave

from .provider import ProviderError
from .realtime_cloud import stream_tts

SAMPLE_RATE = 24000
MAX_AUDIO_BYTES = SAMPLE_RATE * 2 * 120  # 120 seconds of mono PCM16


async def synthesize_wav(settings, text):
    """Buffer one English utterance and wrap its PCM16 samples in a WAV file."""
    pcm = bytearray()
    async with aclosing(stream_tts(settings, text)) as stream:
        async for chunk in stream:
            if len(pcm) + len(chunk) > MAX_AUDIO_BYTES:
                raise ProviderError('Generated speech is too long. Please retry.')
            pcm.extend(chunk)
    if not pcm or len(pcm) % 2:
        raise ProviderError('Speech synthesis returned invalid audio. Please retry.')
    target = BytesIO()
    with wave.open(target, 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(pcm)
    return target.getvalue()
