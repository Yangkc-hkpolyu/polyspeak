import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
import json
import time
import uuid
import wave

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from .avatar import AvatarRenderer
from .bank import SOURCES, catalog
from .config import ROOT, load_settings
from .engine import SpeakingEngine
from .errors import public_error_message
from .media import MediaManager
from .live_avatar import LiveAvatarManager
from .live_routes import live_router
from .streaming_input import streaming_capture
from .pronunciation import PronunciationService
from .provider import ModelProvider, ProviderError
from .schemas import AnswerRequest, ExamSetup, QuestionRequest, SpeechRequest
from .speech import SpeechService
from .store import ConflictError, InterviewStore


def create_app(settings=None, provider=None, speech=None, pronunciation=None, clock=time.time):
    settings = settings or load_settings()
    settings.runtime.mkdir(parents=True, exist_ok=True)
    recordings_folder = settings.runtime / "recordings"
    recordings_folder.mkdir(exist_ok=True)
    store = InterviewStore(settings.runtime / "speaking.sqlite3")
    provider = provider or ModelProvider(settings)
    engine = SpeakingEngine(store, provider, clock)
    speech = speech or SpeechService(settings, provider)
    pronunciation = pronunciation or PronunciationService(settings)
    renderer = AvatarRenderer(settings)
    media = MediaManager(settings.runtime / "media", speech, renderer)
    live = LiveAvatarManager(settings, renderer)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        await live.close()
        await engine.close()
        for task in list(media.tasks):
            task.cancel()
        if media.tasks:
            await asyncio.gather(*media.tasks, return_exceptions=True)
        media.executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="PolySpeak · Speaking Practice", version="3.0.0", lifespan=lifespan)
    app.state.engine, app.state.media = engine, media
    app.state.live = live
    app.include_router(live_router(live, store, engine))

    @app.websocket("/api/speaking/sessions/{session_id}/stt")
    async def stt(websocket: WebSocket, session_id: str, question_id: str):
        await streaming_capture(websocket, session_id, question_id, settings, engine, store, pronunciation, clock)

    @app.middleware("http")
    async def local_origin(request: Request, call_next):
        origin = request.headers.get("origin")
        allowed = {str(request.base_url).rstrip("/"), "http://127.0.0.1:8088", "http://localhost:8088"}
        if origin and origin not in allowed and request.method not in ("GET", "HEAD"):
            return JSONResponse({"detail": "Please send this request from the local application page."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @app.exception_handler(ProviderError)
    async def provider_error(_request, exc):
        return JSONResponse({"detail": public_error_message(exc, "The service request could not be completed. Please try again.", settings)}, status_code=502)

    @app.exception_handler(ConflictError)
    async def conflict_error(_request, exc):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing(_request, _exc):
        return JSONResponse({"detail": "This practice session could not be found. Please start again."}, status_code=404)

    @app.exception_handler(ValueError)
    async def invalid(_request, exc):
        return JSONResponse({"detail": public_error_message(exc, "The request could not be completed. Check your input and try again.", settings)}, status_code=422)

    @app.get("/api/speaking/status")
    async def status():
        output = settings.tts_profile("en")
        return {"name": "PolySpeak", "api_configured": bool(settings.api_key), "chat_model": settings.chat_model, "asr_model": settings.realtime_asr_model, "avatar_available": settings.model_path.is_file() and (settings.avatar_directory / "avatar.json").is_file(), "pronunciation_configured": bool(settings.azure_key), "model_finetuned": False, "format_version": "TOEFL 2026 / IELTS Speaking", "speech_input": "Qwen realtime WebSocket ASR", "speech_output": output["model"], "speech_provider": output["provider"], "speech_voice": output["voice"], "speech_language": output["language"], "avatar": "Nora · PolyInterview LiveTalking", "avatar_pipeline": "livetalking_webrtc", "original_project_modified": False}

    @app.get("/api/speaking/library")
    async def library():
        value = catalog()
        for source in value["sources"]:
            if (ROOT / "speaking-resources/official" / source["filename"]).is_file():
                source["local_url"] = f"/api/speaking/resources/{source['id']}"
        return value

    @app.get("/api/speaking/resources/{source_id}")
    async def resource(source_id: str):
        source = next((x for x in SOURCES if x["id"] == source_id), None)
        if not source:
            raise HTTPException(404, "This resource could not be found.")
        target = ROOT / "speaking-resources/official" / source["filename"]
        if not target.is_file():
            raise HTTPException(404, "The original file has not been downloaded. Open the official source link instead.")
        return FileResponse(target, media_type="application/pdf")

    @app.post("/api/speaking/check-connection")
    async def check_connection():
        result = await provider.complete('Return only {"ok":true}.', {"task": "connection_test"})
        if result.get("ok") is not True:
            raise ProviderError("The connection test did not receive a valid response.")
        return {"ok": True}

    @app.get("/api/speaking/sessions")
    async def history():
        with store.connect() as db:
            rows = db.execute("SELECT data FROM interviews ORDER BY rowid DESC LIMIT 30").fetchall()
        return [{"id": s["id"], "created_at": s["created_at"], "exam": s["setup"]["exam"], "mode": s["setup"]["mode"], "title": s["set_title"], "status": s["status"], "answered": len(s["turns"])} for row in rows for s in [json.loads(row[0])]]

    @app.post("/api/speaking/sessions")
    async def start(setup: ExamSetup):
        return engine.start(setup)

    @app.get("/api/speaking/sessions/{session_id}")
    async def session(session_id: str):
        return engine.public(store.get(session_id))

    @app.post("/api/speaking/sessions/{session_id}/ready")
    async def ready(session_id: str, body: QuestionRequest):
        return await engine.ready(session_id, body.question_id)

    @app.post("/api/speaking/sessions/{session_id}/begin-answer")
    async def begin(session_id: str, body: QuestionRequest):
        return await engine.ready(session_id, body.question_id, begin=True)

    @app.post("/api/speaking/sessions/{session_id}/answers")
    async def answer(session_id: str, body: AnswerRequest):
        return await engine.answer(session_id, body)

    @app.post("/api/speaking/sessions/{session_id}/finish")
    async def finish(session_id: str):
        return await engine.finish(session_id)

    @app.post("/api/speaking/sessions/{session_id}/question-media")
    async def question_media(session_id: str, body: QuestionRequest):
        current = store.get(session_id)
        question = engine.pending(current, body.question_id)
        if len(media.tasks) >= 4:
            raise HTTPException(409, "Speech is already being generated. Please try again shortly.")
        return media.submit(question["text"], "en")

    @app.post("/api/speaking/media")
    async def preview(body: SpeechRequest):
        if len(media.tasks) >= 4:
            raise HTTPException(409, "Speech is already being generated. Please try again shortly.")
        return media.submit(body.text, body.language)

    @app.get("/api/speaking/media/{job_id}")
    async def get_media(job_id: str):
        if job_id not in media.jobs:
            raise HTTPException(404, "This speech clip could not be found. Please play it again.")
        return media.jobs[job_id].copy()

    @app.post("/api/speaking/sessions/{session_id}/capture")
    async def capture(session_id: str, question_id: str = Form(...), audio: UploadFile = File(...)):
        current = store.get(session_id)
        question = engine.pending(current, question_id)
        if current["setup"]["mode"] == "mock" and (question["phase"] == "listening" or question["prepare_until"] > clock()):
            raise ValueError("Wait until the question and preparation time have finished before answering.")
        content = await audio.read(5 * 1024 * 1024 + 1)
        if len(content) > 5 * 1024 * 1024:
            raise ValueError("Recordings must not exceed 5 MB.")
        try:
            with wave.open(BytesIO(content)) as wav:
                duration = wav.getnframes() / wav.getframerate()
                if wav.getnchannels() != 1 or wav.getsampwidth() != 2 or wav.getframerate() != 16000:
                    raise ValueError("Use a 16 kHz mono PCM WAV recording.")
        except (wave.Error, EOFError, ZeroDivisionError) as exc:
            raise ValueError("The recording could not be read. Please record it again.") from exc
        cap = question["answer_seconds"] + 1.5 if current["setup"]["mode"] == "mock" else 125
        if not 0.3 <= duration <= min(cap, 125):
            raise ValueError("The recording length is outside the limit for this question. Please record it again.")
        audio_id = uuid.uuid4().hex
        path = recordings_folder / f"{audio_id}.wav"
        path.write_bytes(content)
        recording = {"id": audio_id, "question_id": question_id, "duration_seconds": round(duration, 2), "text": "", "pronunciation": {"status": "pending"}}
        # Save first so an ASR outage cannot discard a student's only recording.
        await engine.store_recording(session_id, question_id, recording)
        async def transcribe():
            try:
                recording["text"] = await speech.transcribe(content, "en")
            except (ProviderError, ValueError) as exc:
                recording["transcription_error"] = str(exc)
        async def assess():
            recording["pronunciation"] = await pronunciation.assess(path, question["text"] if question["task_type"] == "repeat" else "")
        await asyncio.gather(transcribe(), assess())
        await engine.store_recording(session_id, question_id, recording)
        return recording

    @app.get("/api/speaking/sessions/{session_id}/recordings/{audio_id}")
    async def recording(session_id: str, audio_id: str):
        current = store.get(session_id)
        if audio_id not in current["recordings"]:
            raise HTTPException(404, "This recording could not be found.")
        return FileResponse(recordings_folder / f"{audio_id}.wav", media_type="audio/wav")

    @app.get("/api/speaking/sessions/{session_id}/export")
    async def export(session_id: str):
        current = store.get(session_id)
        if not current["report"]:
            raise HTTPException(409, "Feedback has not been generated yet.")
        payload = {"created_at": current["created_at"], "setup": current["setup"], "set_title": current["set_title"], "report": engine.public(current)["report"], "turns": current["turns"]}
        return Response(json.dumps(payload, ensure_ascii=False, indent=2), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="polyspeak-feedback.json"'})

    app.mount("/media", StaticFiles(directory=settings.runtime / "media"), name="media")
    app.mount("/speaking-assets", StaticFiles(directory=ROOT / "backend/speaking/assets"), name="assets")
    # The speaking entry is built from the copied Vue frontend. Legacy source remains in the copy.
    app.mount("/", StaticFiles(directory=ROOT / "frontend/dist-speaking", html=True, check_dir=False), name="frontend")
    return app


app = create_app()
