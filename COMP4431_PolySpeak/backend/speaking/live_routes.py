"""Signalling and utterance control; audio/video themselves travel over WebRTC."""
from fastapi import APIRouter, Request
from pydantic import Field
from typing import Literal

from .schemas import StrictInput, SpeechRequest, QuestionRequest


class OfferRequest(StrictInput):
    sdp: str = Field(min_length=1, max_length=100000)
    type: Literal["offer"]


def live_router(manager, store, engine):
    router = APIRouter(prefix="/api/speaking/live")

    @router.post("/offer")
    async def offer(body: OfferRequest):
        return await manager.offer(body.sdp, body.type)

    @router.post("/{live_id}/preview")
    async def preview(live_id: str, body: SpeechRequest):
        return manager.get(live_id).speak(body.text)

    @router.post("/{live_id}/question/{session_id}")
    async def question(live_id: str, session_id: str, body: QuestionRequest):
        current = store.get(session_id)
        question = engine.pending(current, body.question_id)
        return manager.get(live_id).speak(question["text"], body.question_id)

    @router.get("/{live_id}/jobs/{job_id}")
    async def job(live_id: str, job_id: str):
        return dict(manager.get(live_id).jobs[job_id])

    @router.post("/{live_id}/interrupt")
    async def interrupt(live_id: str):
        manager.get(live_id).interrupt()
        return {"ok": True}

    @router.delete("/{live_id}")
    @router.post("/{live_id}/close")
    async def close(live_id: str):
        await manager.get(live_id).close()
        return {"ok": True}

    return router
