"""Qwen realtime protocol and language-specific speech sources for LiveTalking."""
import asyncio
import base64
import io
import json
from urllib.parse import urlsplit
import uuid

import av
import edge_tts
import websockets

from .provider import ProviderError


def event(kind, **values):
    return {"type": kind, "event_id": uuid.uuid4().hex, **values}


def realtime_url(settings, model):
    base = settings.realtime_url or "wss://" + urlsplit(settings.base_url).netloc + "/api-ws/v1/realtime"
    return base + "?model=" + model


async def connect(settings, model):
    if not settings.api_key:
        raise ProviderError("The live speech service API key is not configured.")
    try:
        return await websockets.connect(realtime_url(settings, model),
                                        additional_headers={"Authorization": "Bearer " + settings.api_key},
                                        open_timeout=15, close_timeout=3, max_size=4 * 1024 * 1024)
    except Exception as exc:
        raise ProviderError("The live speech connection failed. Check your network, service region, and model access.") from exc


async def receive_until(connection, expected, timeout=20):
    async with asyncio.timeout(timeout):
        while True:
            item = json.loads(await connection.recv())
            if item.get("type") == "error":
                raise ProviderError("The live speech service rejected the request. Check model access and configuration.")
            if item.get("type") == expected:
                return item


async def stream_tts(settings, text, language="en"):
    """Yield PCM16/24kHz from the selected provider, without a silent fallback."""
    profile = settings.tts_profile(language)
    source = stream_edge_tts if profile["provider"] == "edgetts" else stream_qwen_tts
    async for pcm in source(settings, text, profile):
        yield pcm


async def stream_edge_tts(settings, text, profile):
    # Preserve PolyInterview's EdgeTTS boundary: finish the utterance download,
    # then decode it. LiveTalking still produces live video from these samples.
    encoded = io.BytesIO()
    async with asyncio.timeout(90):
        async for item in edge_tts.Communicate(text, profile["voice"],
                                               connect_timeout=15, receive_timeout=30).stream():
            if item["type"] == "audio":
                encoded.write(item["data"])
    if not encoded.tell():
        raise ProviderError("The selected speech service returned no audio.")
    encoded.seek(0)
    converter = av.AudioResampler(format="s16", layout="mono", rate=24000)
    with av.open(encoded, format="mp3") as container:
        for frame in container.decode(audio=0):
            for converted in converter.resample(frame):
                yield converted.to_ndarray().astype("<i2", copy=False).tobytes()
        for converted in converter.resample(None):
            yield converted.to_ndarray().astype("<i2", copy=False).tobytes()


async def stream_qwen_tts(settings, text, profile):
    connection = await connect(settings, settings.realtime_tts_model)
    try:
        await receive_until(connection, "session.created")
        await connection.send(json.dumps(event("session.update", session={
            "mode": "commit", "voice": profile["voice"],
            "language_type": "English" if profile["language"] == "en" else "Chinese",
            "response_format": "pcm", "sample_rate": 24000})))
        await receive_until(connection, "session.updated")
        await connection.send(json.dumps(event("input_text_buffer.append", text=text)))
        await connection.send(json.dumps(event("input_text_buffer.commit")))
        await connection.send(json.dumps(event("session.finish")))
        async with asyncio.timeout(90):
            async for message in connection:
                item = json.loads(message)
                if item.get("type") == "response.audio.delta":
                    yield base64.b64decode(item["delta"], validate=True)
                elif item.get("type") == "session.finished":
                    return
                elif item.get("type") == "error":
                    raise ProviderError("Live speech synthesis failed. Check access to this model.")
    finally:
        await connection.close()
