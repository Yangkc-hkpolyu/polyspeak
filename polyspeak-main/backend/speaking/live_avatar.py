"""PolyInterview's original LiveTalking player, inference scheduler and RTC session."""
import asyncio
import json
from queue import Queue
from types import SimpleNamespace
import uuid

import cv2
import numpy as np
import torch
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription, RTCRtpSender

from .avatar import apply_scene_face_mask
from .errors import public_error_message
from .provider import ProviderError
from .vendor.livetalking.gpu_inference_scheduler import GPUInferenceScheduler
from .vendor.livetalking.lipreal import LipReal
from .vendor.livetalking.webrtc import HumanPlayer


class SpeakingLipReal(LipReal):
    """Scene and cadence overrides; media queues/inference/render loop stay upstream."""
    def __init__(self, renderer, scheduler, settings, owner):
        self.renderer, self.owner = renderer, owner
        options = SimpleNamespace(fps=50, batch_size=8, l=10, r=10,
                                  transport="webrtc", customopt=[],
                                  sessionid=int(owner.id[:8], 16), speaking_settings=settings)
        avatar = (renderer.frames, renderer.face_frames, renderer.coords)
        super().__init__(options, avatar, scheduler, renderer.device)
        self.asr.queue = Queue(maxsize=200)

    def _mirror_index(self, index):
        cycle = self.renderer.playback_cycle
        return cycle[index % len(cycle)]

    def _build_frame_gpu_cycle(self, _device):
        # Scene masks are applied on paste-back; never bypass them with raw GPU paste.
        return None

    def _paste_back_frame_tensor_yuv(self, _prediction, _index):
        return None

    def _paste_back_frame_tensor(self, prediction, index):
        return self.paste_back_frame(prediction.detach().float().cpu().numpy(), index)

    def paste_back_frame(self, prediction, index):
        frame = super().paste_back_frame(prediction, index)
        return apply_scene_face_mask(frame, self.renderer.frames[index], self.renderer.coords[index], self.renderer.scene_masks[index])

    def live_event(self, event):
        self.owner.send_thread(event)

    def notify(self, eventpoint):
        if eventpoint and eventpoint.get("job_id"):
            self.live_event({"type": "speech." + eventpoint.get("status", "event"),
                             "job_id": eventpoint["job_id"]})


class LiveSession:
    def __init__(self, manager):
        self.id = uuid.uuid4().hex
        self.manager, self.loop = manager, asyncio.get_running_loop()
        self.pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
        self.dc = self.player = self.avatar = None
        self.jobs = {}
        self.closed = False
        self.expiry = None

    def get_session_dc_and_loop(self, _sessionid):
        return self.loop, self.dc

    def send_thread(self, event):
        try:
            self.loop.call_soon_threadsafe(self.send, event)
        except RuntimeError:
            pass

    def send(self, event):
        if event["type"] == "speech.error":
            event = {**event, "message": public_error_message(event.get("message", ""), "Live speech could not be completed. Check your connection and try again.", self.manager.settings)}
        job = self.jobs.get(event.get("job_id"))
        if job is not None and job["status"] == "interrupted" and event["type"] != "speech.interrupted":
            return
        if job is not None:
            if event["type"] == "speech.start":
                job["status"] = "speaking"
            elif event["type"] == "speech.end":
                job["status"] = "completed"
            elif event["type"] == "speech.error":
                job.update(status="failed", error=event["message"])
        if self.dc and self.dc.readyState == "open":
            self.dc.send(json.dumps(event))

    def speak(self, text, question_id=None):
        if self.closed or self.pc.connectionState != "connected":
            raise ValueError("The live avatar connection is not ready. Reconnect and try again.")
        if any(job["status"] in ("queued", "speaking") for job in self.jobs.values()):
            raise ValueError("The avatar is speaking. Wait for it to finish or stop the current speech.")
        job = {"id": uuid.uuid4().hex, "status": "queued", "transport": "webrtc", "question_id": question_id}
        self.jobs[job["id"]] = job
        self.avatar.put_msg_txt(text, {"job_id": job["id"]})
        if len(self.jobs) > 30:
            oldest = next(iter(self.jobs))
            if self.jobs[oldest]["status"] not in ("queued", "speaking"):
                del self.jobs[oldest]
        return dict(job)

    def interrupt(self):
        if self.avatar:
            self.avatar.flush_talk()
        for job in self.jobs.values():
            if job["status"] in ("queued", "speaking"):
                job["status"] = "interrupted"
                self.send({"type": "speech.interrupted", "job_id": job["id"]})

    async def close(self):
        if self.closed:
            return
        self.closed = True
        if self.expiry:
            self.expiry.cancel()
        self.interrupt()
        await self.pc.close()
        if self.player:
            # HumanPlayer stops and joins its producer after both tracks stop.
            await asyncio.to_thread(self.player.audio.stop)
            await asyncio.to_thread(self.player.video.stop)
        if self.avatar and self.avatar.tts.thread:
            await asyncio.to_thread(self.avatar.tts.thread.join, 2)
        self.manager.sessions.pop(self.id, None)


class LiveAvatarManager:
    def __init__(self, settings, renderer):
        self.settings, self.renderer = settings, renderer
        self.sessions = {}
        self.scheduler = None
        self.load_lock = asyncio.Lock()

    async def ensure_model(self):
        async with self.load_lock:
            if self.scheduler is not None:
                return
            await asyncio.to_thread(self._load)
            self.scheduler = GPUInferenceScheduler({self.renderer.device: self.renderer.model},
                                                   max_super_batch=32, queue_maxsize=32)
            self.scheduler.start()

    def _load(self):
        with self.renderer.lock:
            self.renderer.load()
            with torch.inference_mode():
                mel = torch.zeros((8, 1, 80, 16), device=self.renderer.device)
                face = torch.from_numpy(self.renderer.face_inputs[:8].copy()).to(self.renderer.device)
                self.renderer.model(mel, face)

    async def offer(self, sdp, description_type):
        if len(self.sessions) >= 2:
            raise ValueError("All avatar connections are in use. Close other practice pages and try again.")
        await self.ensure_model()
        if len(self.sessions) >= 2:
            raise ValueError("All avatar connections are in use. Close other practice pages and try again.")
        session = LiveSession(self)
        self.sessions[session.id] = session
        try:
            session.avatar = await asyncio.to_thread(SpeakingLipReal, self.renderer, self.scheduler, self.settings, session)
            session.avatar.attach_session_mgr(session)
            session.player = HumanPlayer(session.avatar, event_loop=session.loop)

            @session.pc.on("datachannel")
            def datachannel(channel):
                if channel.label == "dh-state":
                    session.dc = channel

            @session.pc.on("connectionstatechange")
            async def connection_changed():
                if session.pc.connectionState in ("closed", "failed"):
                    asyncio.create_task(session.close())
                elif session.pc.connectionState == "disconnected":
                    session.expiry = asyncio.get_running_loop().call_later(10, lambda: asyncio.create_task(session.close()))
                elif session.pc.connectionState == "connected" and session.expiry:
                    session.expiry.cancel()
                    session.expiry = None

            await session.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=description_type))
            session.pc.addTrack(session.player.audio)
            session.pc.addTrack(session.player.video)
            for transceiver in session.pc.getTransceivers():
                if transceiver.kind == "video":
                    codecs = RTCRtpSender.getCapabilities("video").codecs
                    transceiver.setCodecPreferences([c for c in codecs if c.mimeType == "video/H264"] +
                                                     [c for c in codecs if c.mimeType != "video/H264"])
            await session.pc.setLocalDescription(await session.pc.createAnswer())
            session.expiry = session.loop.call_later(35, lambda: asyncio.create_task(session.close())
                                                    if session.pc.connectionState != "connected" else None)
            return {"sdp": session.pc.localDescription.sdp, "type": session.pc.localDescription.type,
                    "live_id": session.id, "transport": "webrtc"}
        except Exception:
            await session.close()
            raise

    def get(self, identifier):
        session = self.sessions.get(identifier)
        if not session or session.closed:
            raise KeyError(identifier)
        return session

    async def close(self):
        await asyncio.gather(*(session.close() for session in list(self.sessions.values())), return_exceptions=True)
        if self.scheduler:
            await asyncio.to_thread(self.scheduler.stop)
