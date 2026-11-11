"""Live PCM/ASR relay following PolyInterview streamstt's event mapping."""
import asyncio
import base64
from collections import OrderedDict
from io import BytesIO
import json
import uuid
import wave

from fastapi import WebSocketDisconnect

from .provider import ProviderError
from .realtime_cloud import connect, event, receive_until


def transcript_event(response, finals):
    """Return visible interim text without duplicating finalised speech segments."""
    kind = response.get("type")
    identifier = response.get("item_id", "current")
    if kind == "conversation.item.input_audio_transcription.completed":
        text = response.get("transcript", "").strip()
        if text:
            finals[identifier] = text
        return {"type": "transcript", "text": " ".join(finals.values()), "final": True}
    if kind == "conversation.item.input_audio_transcription.text":
        text, stash = response.get("text", ""), response.get("stash", "")
        partial = text + stash if not stash.startswith(text) else stash
        previous = " ".join(value for key, value in finals.items() if key != identifier)
        return {"type": "transcript", "text": (previous + " " + partial).strip(), "final": False}
    return None


async def streaming_capture(websocket, session_id, question_id, settings, engine, store, pronunciation, clock):
    # HTTP middleware does not protect WebSocket upgrades.
    origin = websocket.headers.get("origin")
    authority = websocket.url.netloc
    allowed = {"http://" + authority, "https://" + authority,
               "http://127.0.0.1:8088", "http://localhost:8088"}
    if origin and origin not in allowed:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    upstream = reader = None
    pcm = bytearray()
    finals = OrderedDict()
    error = None
    client_gone = False
    async def send(value):
        if not client_gone:
            await websocket.send_json(value)
    try:
        session = store.get(session_id)
        question = engine.pending(session, question_id)
        if session["setup"]["mode"] == "mock" and (
                question["phase"] == "listening" or (question["prepare_until"] or 0) > clock()):
            raise ValueError("请在问题播放和准备环节结束后开始作答。")
        cap = min(125, question["answer_seconds"] + 1.5) if session["setup"]["mode"] == "mock" else 125
        upstream = await connect(settings, settings.realtime_asr_model)
        await receive_until(upstream, "session.created")
        await upstream.send(json.dumps(event("session.update", session={
            "modalities": ["text"], "input_audio_format": "pcm", "sample_rate": 16000,
            "input_audio_transcription": {"language": "en"},
            "turn_detection": {"type": "server_vad", "threshold": 0.2, "silence_duration_ms": 800}})))
        await receive_until(upstream, "session.updated")
        finished = asyncio.Event()
        async def receive_results():
            nonlocal error
            try:
                async for message in upstream:
                    value = json.loads(message)
                    payload = transcript_event(value, finals)
                    if payload:
                        await send(payload)
                    if value.get("type") == "error":
                        error = "实时识别服务本次未完成；已收到的录音将保留。"
                        break
                    if value.get("type") == "session.finished":
                        break
            except Exception:
                error = "实时识别连接中断，转写可能不完整。"
            finally:
                finished.set()
        reader = asyncio.create_task(receive_results())
        await send({"type": "ready", "sample_rate": 16000, "format": "pcm16", "model": settings.realtime_asr_model})
        deadline = asyncio.get_running_loop().time() + cap + 15
        while True:
            try:
                incoming = await asyncio.wait_for(websocket.receive(), timeout=max(0.01, deadline - asyncio.get_running_loop().time()))
            except WebSocketDisconnect:
                client_gone = True
                break
            if incoming["type"] == "websocket.disconnect":
                client_gone = True
                break
            content = incoming.get("bytes")
            if content is not None:
                if len(content) % 2 or len(content) > 64000:
                    raise ValueError("实时录音应为 16 kHz 单声道 PCM16 分块。")
                remaining = max(0, int(cap * 32000) - len(pcm))
                chunk = content[:remaining]
                pcm.extend(chunk)
                if chunk:
                    await upstream.send(json.dumps(event("input_audio_buffer.append", audio=base64.b64encode(chunk).decode("ascii"))))
                if len(pcm) >= int(cap * 32000):
                    break
            elif incoming.get("text"):
                control = json.loads(incoming["text"])
                if control.get("type") in ("finish", "flush"):
                    break
        await upstream.send(json.dumps(event("session.finish")))
        try:
            await asyncio.wait_for(finished.wait(), 15)
        except TimeoutError:
            error = "录音已保存，最终转写等待超时，结果可能不完整。"
    except (ValueError, KeyError, ProviderError) as exc:
        error = str(exc) if isinstance(exc, (ValueError, ProviderError)) else "找不到本次练习。"
    except Exception:
        error = "实时语音连接中断；已收到的录音将保留。"
    finally:
        if reader:
            reader.cancel()
            await asyncio.gather(reader, return_exceptions=True)
        if upstream:
            await upstream.close()
    try:
        if len(pcm) < 9600:
            await send({"type": "error", "message": error or "录音太短，请至少说完一句话。"})
            await websocket.close()
            return
        identifier = uuid.uuid4().hex
        path = settings.runtime / "recordings" / (identifier + ".wav")
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(pcm)
        recording = {"id": identifier, "question_id": question_id,
                     "duration_seconds": round(len(pcm) / 32000, 2),
                     "text": " ".join(finals.values()), "transcript_source": "qwen_realtime_websocket",
                     "pronunciation": {"status": "pending"}}
        if error:
            recording["transcription_error"] = error
        await engine.store_recording(session_id, question_id, recording)
        recording["pronunciation"] = await pronunciation.assess(path, question["text"] if question["task_type"] == "repeat" else "")
        await engine.store_recording(session_id, question_id, recording)
        await send({"type": "recording.saved", "recording": recording})
        if not client_gone:
            await websocket.close()
    except (WebSocketDisconnect, RuntimeError, KeyError, ValueError):
        # A closed client must not prevent the already-written recording being retained.
        return
