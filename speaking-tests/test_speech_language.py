import asyncio
import base64
from dataclasses import replace
import io
import json

import av
import numpy as np
import pytest

from backend.speaking import config, realtime_cloud
from backend.speaking.config import Settings


def encoded_tone():
    """Produce a real MP3 locally so the decoder boundary is exercised offline."""
    data = io.BytesIO()
    with av.open(data, mode="w", format="mp3") as container:
        stream = container.add_stream("libmp3lame", rate=24000)
        stream.layout = "mono"
        samples = (np.sin(np.arange(14400) * 2 * np.pi * 220 / 24000) * .2).astype(np.float32)
        frame = av.AudioFrame.from_ndarray(samples.reshape(1, -1), format="fltp", layout="mono")
        frame.sample_rate = 24000
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
    return data.getvalue()


@pytest.mark.parametrize("language,voice", [("en", "en-US-JennyNeural"), ("zh", "zh-CN-XiaoxiaoNeural")])
def test_live_edge_uses_matching_voice_and_waits_for_complete_audio(monkeypatch, language, voice):
    async def run():
        first, finish = asyncio.Event(), asyncio.Event()
        encoded = encoded_tone()
        calls = []

        class Edge:
            def __init__(self, text, selected_voice, **kwargs):
                calls.append((text, selected_voice))

            async def stream(self):
                yield {"type": "audio", "data": encoded[:len(encoded)//2]}
                first.set()
                await finish.wait()
                yield {"type": "audio", "data": encoded[len(encoded)//2:]}

        async def collect():
            return b"".join([chunk async for chunk in realtime_cloud.stream_tts(Settings(), "sample", language)])

        monkeypatch.setattr(realtime_cloud.edge_tts, "Communicate", Edge)
        task = asyncio.create_task(collect())
        await asyncio.wait_for(first.wait(), 2)
        assert not task.done(), "Incomplete source audio must not be published"
        finish.set()
        pcm = await asyncio.wait_for(task, 2)
        samples = np.frombuffer(pcm, dtype="<i2")
        assert calls == [("sample", voice)]
        assert .5 < len(samples) / 24000 < .8
        assert np.max(np.abs(samples)) > 1000

    asyncio.run(run())


@pytest.mark.parametrize("language,wire_language", [("en", "English"), ("zh", "Chinese")])
def test_explicit_qwen_alternative_sends_the_requested_language(monkeypatch, language, wire_language):
    class Connection:
        def __init__(self):
            self.sent = []
            self.responses = iter([{"type": "session.created"}, {"type": "session.updated"}])
            self.closed = False

        async def recv(self):
            return json.dumps(next(self.responses))

        async def send(self, message):
            self.sent.append(json.loads(message))

        def __aiter__(self):
            async def audio():
                yield json.dumps({"type": "response.audio.delta", "delta": base64.b64encode(b"\x01\x00" * 320).decode()})
                yield json.dumps({"type": "session.finished"})
            return audio()

        async def close(self):
            self.closed = True

    connection = Connection()

    async def connect(_settings, _model):
        return connection

    async def run():
        settings = replace(Settings(), tts_provider="qwen")
        audio = b"".join([chunk async for chunk in realtime_cloud.stream_tts(settings, "sample", language)])
        assert audio == b"\x01\x00" * 320
        session = next(e["session"] for e in connection.sent if e["type"] == "session.update")
        assert session["language_type"] == wire_language
        assert session["voice"] == "Cherry"
        assert connection.closed

    monkeypatch.setattr(realtime_cloud, "connect", connect)
    asyncio.run(run())


def test_english_request_rejects_a_chinese_edge_voice():
    settings = replace(Settings(), voice_en="zh-CN-XiaoxiaoNeural")
    with pytest.raises(ValueError, match="does not match"):
        settings.tts_profile("en")


def test_provider_and_language_voices_are_loaded_from_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setenv("SPEAKING_TTS_PROVIDER", "edgetts")
    monkeypatch.setenv("SPEAKING_VOICE_EN", "en-GB-SoniaNeural")
    monkeypatch.setenv("SPEAKING_VOICE_ZH", "zh-CN-XiaoxiaoNeural")
    settings = config.load_settings()
    assert settings.tts_profile("en")["voice"] == "en-GB-SoniaNeural"
    assert settings.tts_profile("zh")["voice"] == "zh-CN-XiaoxiaoNeural"


def test_edge_failure_does_not_silently_switch_provider(monkeypatch):
    class Edge:
        def __init__(self, *_args, **_kwargs):
            pass

        async def stream(self):
            raise ConnectionError("Test connection failure")
            yield

    async def forbidden(*_args, **_kwargs):
        pytest.fail("The configured voice must not silently change on an error")
        yield

    async def run():
        with pytest.raises(ConnectionError):
            _ = [chunk async for chunk in realtime_cloud.stream_tts(Settings(), "sample")]

    monkeypatch.setattr(realtime_cloud.edge_tts, "Communicate", Edge)
    monkeypatch.setattr(realtime_cloud, "stream_qwen_tts", forbidden)
    asyncio.run(run())
