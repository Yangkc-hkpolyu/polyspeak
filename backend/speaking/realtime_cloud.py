"""Qwen realtime wire protocol used by the original PolyInterview STT service."""
import asyncio
import base64
import json
from urllib.parse import urlsplit
import uuid

import websockets

from .provider import ProviderError


def event(kind, **values):
    return {"type": kind, "event_id": uuid.uuid4().hex, **values}


def realtime_url(settings, model):
    base = settings.realtime_url or "wss://" + urlsplit(settings.base_url).netloc + "/api-ws/v1/realtime"
    return base + "?model=" + model


async def connect(settings, model):
    if not settings.api_key:
        raise ProviderError("实时语音服务尚未配置 API Key。")
    try:
        return await websockets.connect(realtime_url(settings, model),
                                        additional_headers={"Authorization": "Bearer " + settings.api_key},
                                        open_timeout=15, close_timeout=3, max_size=4 * 1024 * 1024)
    except Exception as exc:
        raise ProviderError("实时语音连接失败，请检查网络、服务地域和模型权限。") from exc


async def receive_until(connection, expected, timeout=20):
    async with asyncio.timeout(timeout):
        while True:
            item = json.loads(await connection.recv())
            if item.get("type") == "error":
                raise ProviderError("实时语音服务拒绝了请求，请检查模型权限和配置。")
            if item.get("type") == expected:
                return item


async def stream_tts(settings, text):
    """Yield PCM16/24kHz chunks as they arrive, before the full utterance exists."""
    connection = await connect(settings, settings.realtime_tts_model)
    try:
        await receive_until(connection, "session.created")
        await connection.send(json.dumps(event("session.update", session={
            "mode": "commit", "voice": "Cherry", "language_type": "English",
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
                    raise ProviderError("实时语音合成失败，请检查该模型的使用权限。")
    finally:
        await connection.close()
