"""PolyInterview's original LiveTalking player, inference scheduler and RTC session."""
import asyncio
from dataclasses import replace
import json
from queue import Empty, Full, Queue
from threading import Event, Thread, local
import time
from types import SimpleNamespace
import uuid

import cv2
import numpy as np
import torch
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription, RTCRtpSender

from .avatar import apply_scene_face_mask
from .errors import public_error_message
from .provider import ProviderError
from .vendor.livetalking.gpu_inference_scheduler import GPUInferenceScheduler, InferenceRequest
from .vendor.livetalking.lipreal import LipReal
from .media_clock import PairedHumanPlayer
from .video_encoder import install_speaking_encoder

install_speaking_encoder()


class OrderedBatchScheduler:
    """Finish one session batch before its producer can emit later silence."""
    def __init__(self, scheduler, stopped, current_epoch, batch_epoch, stats):
        self.scheduler, self.stopped = scheduler, stopped
        self.current_epoch, self.batch_epoch, self.stats = current_epoch, batch_epoch, stats

    def submit(self, request):
        epoch = self.batch_epoch()
        active = lambda: not self.stopped() and self.current_epoch() == epoch
        if not active():
            return
        # Each request owns its mailbox, so a late cancelled result cannot be
        # mistaken for the next utterance's result.
        mailbox = Queue(maxsize=1)
        started = time.monotonic()
        self.scheduler.submit(replace(request, result_queue=mailbox))
        self.stats["gpu_batches"] += 1
        try:
            while active():
                try:
                    result = mailbox.get(timeout=0.05)
                    break
                except Empty:
                    continue
            else:
                self.stats["cancelled_gpu_batches"] += 1
                return
            while active():
                try:
                    if hasattr(request.result_queue, "put_for_epoch"):
                        request.result_queue.put_for_epoch(result, epoch, timeout=0.05)
                    else:
                        request.result_queue.put(result, timeout=0.05)
                    return
                except Full:
                    continue
            self.stats["cancelled_gpu_batches"] += 1
        finally:
            elapsed = time.monotonic() - started
            self.stats["gpu_wait_seconds"] += elapsed
            self.stats["max_gpu_wait_seconds"] = max(self.stats["max_gpu_wait_seconds"], elapsed)


class EpochResultQueue(Queue):
    """Associate output batches with the utterance generation that produced them."""
    def __init__(self, maxsize, epoch, output_epoch):
        super().__init__(maxsize)
        self.epoch, self.output_epoch = epoch, output_epoch

    def put(self, item, block=True, timeout=None):
        self.put_for_epoch(item, self.epoch(), block=block, timeout=timeout)

    def put_for_epoch(self, item, epoch, block=True, timeout=None):
        super().put((epoch, item), block=block, timeout=timeout)

    def get(self, block=True, timeout=None):
        epoch, item = super().get(block=block, timeout=timeout)
        self.output_epoch.value = epoch
        return item

    def pending_frames(self):
        with self.mutex:
            return sum(len(item) if isinstance(item, list) else 1 for _, item in self.queue)


class EpochOutputTrack:
    """Suppress only frames invalidated by an explicit interruption."""
    def __init__(self, track, avatar):
        self.track, self.avatar = track, avatar

    def __getattr__(self, name):
        return getattr(self.track, name)

    def put_frame_nowait(self, item):
        if getattr(self.avatar._output_epoch, "value", None) != self.avatar._stream_epoch:
            self.avatar.stats["cancelled_output_frames"] += 1
            return False
        return self.track.put_frame_nowait(item)


def media_reserve_seconds(audio_track, video_track, pending_video_frames=0):
    """Conservative queued duration; neither stream may hold the other empty."""
    reserves = []
    for track, frame_seconds in ((audio_track, 0.02), (video_track, 0.04)):
        if track is not None:
            queued = track._queue.qsize()
            async_queue = getattr(track, "_async_queue", None)
            if async_queue is not None:
                queued += async_queue.qsize()
            reserves.append(queued * frame_seconds)
    return min(reserves, default=0.0) + pending_video_frames * 0.04


class SpeakingLipReal(LipReal):
    """Scene, ordered inference, and paced production around upstream rendering."""
    def __init__(self, renderer, scheduler, settings, owner):
        self.renderer, self.owner = renderer, owner
        self._stream_epoch = self._render_epoch = 0
        self._render_quit = None
        self._flush_requested, self._producer_wake = Event(), Event()
        self._audio_track = self._video_track = None
        self._output_epoch = local()
        self._active_audio_job = None
        self.stats = {"gpu_batches": 0, "cancelled_gpu_batches": 0,
                      "gpu_wait_seconds": 0.0, "max_gpu_wait_seconds": 0.0,
                      "producer_wait_seconds": 0.0, "max_media_reserve_seconds": 0.0,
                      "audio_input_frames": 0, "speech_starts": 0, "speech_ends": 0,
                      "audio_input_silence_frames_during_speech": 0, "source_underrun_frames": 0,
                      "quiet_lip_frames": 0,
                      "audio_dropped_frames": 0, "video_dropped_frames": 0,
                      "cancelled_output_frames": 0}
        options = SimpleNamespace(fps=50, batch_size=8, l=10, r=10,
                                  transport="webrtc", customopt=[],
                                  sessionid=int(owner.id[:8], 16), speaking_settings=settings)
        avatar = (renderer.frames, renderer.face_frames, renderer.coords)
        super().__init__(options, avatar, scheduler, renderer.device)
        self.res_frame_queue = EpochResultQueue(self.batch_size * 6, lambda: self._render_epoch, self._output_epoch)
        self.asr.queue = Queue(maxsize=200)
        self._scheduler = OrderedBatchScheduler(scheduler, self._stopped,
            lambda: self._stream_epoch, lambda: self._render_epoch, self.stats)
        self._source_audio_frame = self.asr.get_audio_frame
        self.asr.get_audio_frame = self._get_audio_frame

    def _stopped(self):
        return self.owner.closed or (self._render_quit is not None and self._render_quit.is_set())

    def _get_audio_frame(self):
        frame, kind, metadata = self._source_audio_frame()
        self.stats["audio_input_frames"] += 1
        status = metadata.get("status") if isinstance(metadata, dict) else None
        if status == "start":
            self._active_audio_job = metadata.get("job_id", True)
            self.stats["speech_starts"] += 1
        if kind == 1 and self._active_audio_job is not None:
            self.stats["audio_input_silence_frames_during_speech"] += 1
            self.stats["source_underrun_frames"] += 1
        if status == "end":
            self._active_audio_job = None
            self.stats["speech_ends"] += 1
        if kind == 0 and isinstance(metadata, dict) and (metadata.get("lip_silent") or status == "end"):
            # Rendering silence is independent of transport underflow. Preserve
            # the exact PCM and its clock, but use the neutral frame for padding.
            kind = 1
            self.stats["quiet_lip_frames"] = self.stats.get("quiet_lip_frames", 0) + 1
        return frame, kind, metadata

    def flush_talk(self):
        self._stream_epoch += 1
        self.tts.flush_talk()
        self._flush_requested.set()
        self._producer_wake.set()
        for track in (self._audio_track, self._video_track):
            async_queue = getattr(track, "_async_queue", None)
            if async_queue is not None:
                self.owner.loop.call_soon_threadsafe(self._empty_queue, async_queue)

    @staticmethod
    def _empty_queue(target):
        if target is not None:
            while True:
                try:
                    target.get_nowait()
                except (Empty, asyncio.QueueEmpty):
                    return

    def _reset_interrupted_audio(self):
        # Perform feature resets on the producer thread, not concurrently with
        # run_step(). Only an explicit stop discards queued utterance frames.
        epoch = self._stream_epoch
        self.asr.flush_talk()
        context = self.asr.stride_left_size + self.asr.stride_right_size
        self.asr.frames = [np.zeros(self.asr.chunk, np.float32) for _ in range(context)]
        for _ in range(self.asr.stride_right_size):
            self.asr.output_queue.put((np.zeros(self.asr.chunk, np.float32), 1, None))
        self._empty_queue(self.res_frame_queue)
        for track in (self._audio_track, self._video_track):
            if track is not None:
                self._empty_queue(track._queue)
        self._active_audio_job = None
        if epoch == self._stream_epoch:
            self._flush_requested.clear()

    def _pending_video_frames(self):
        return self.res_frame_queue.pending_frames()

    def prepare_speech(self):
        # After an idle period the laptop GPU may need > 1 s to wake up.
        # Run the actual scheduler/copy path before publishing any utterance PCM;
        # neutral live frames keep playing and audio/video clocks stay together.
        started = time.monotonic()
        mailbox = Queue(maxsize=1)
        count = self.batch_size
        self.owner.manager.scheduler.submit(InferenceRequest(
            device_id=self.renderer.device, session_id=self.opt.sessionid,
            mel_batch=np.zeros((count, 1, 80, 16), dtype=np.float32),
            img_batch=np.ascontiguousarray(self.renderer.face_inputs[np.arange(count) % len(self.renderer.face_inputs)]),
            audio_frames=[(np.zeros(320, np.float32), 1, None)] * (count * 2),
            frame_indices=list(range(count)), result_queue=mailbox))
        result = mailbox.get(timeout=30)
        if not result or any(item[0] is None for item in result):
            raise RuntimeError("The avatar could not prepare speech frames.")
        self.stats["speech_warmup_seconds"] = time.monotonic() - started

    def render(self, quit_event, loop=None, audio_track=None, video_track=None):
        self._render_quit = quit_event
        self._audio_track, self._video_track = audio_track, video_track
        self.init_customindex()
        self.tts.render(quit_event)
        process_quit = Event()
        process_thread = Thread(target=self.process_frames,
            args=(process_quit, loop,
                  EpochOutputTrack(audio_track, self) if audio_track is not None else None,
                  EpochOutputTrack(video_track, self) if video_track is not None else None),
            name="speaking-frame-output")
        process_thread.start()
        # One 320 ms batch plus processing headroom. Keep the normal 50 Hz audio
        # and 25 Hz video clocks; only control how far production runs ahead.
        reserve_target = self.batch_size * 0.04 + 0.16
        try:
            while not self._stopped():
                if self._flush_requested.is_set():
                    self._reset_interrupted_audio()
                reserve = media_reserve_seconds(audio_track, video_track, self._pending_video_frames())
                self.stats["max_media_reserve_seconds"] = max(self.stats["max_media_reserve_seconds"], reserve)
                self.stats["audio_dropped_frames"] = getattr(audio_track, "_drop_count", 0)
                self.stats["video_dropped_frames"] = getattr(video_track, "_drop_count", 0)
                if reserve > reserve_target:
                    started = time.monotonic()
                    self._producer_wake.wait(min(reserve - reserve_target, 0.05))
                    self._producer_wake.clear()
                    self.stats["producer_wait_seconds"] += time.monotonic() - started
                    continue
                self._render_epoch = self._stream_epoch
                self.asr.run_step()
                if self._render_epoch == self._stream_epoch:
                    self._drain_inference_batches()
        finally:
            process_quit.set()
            process_thread.join(timeout=2.0)

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

    def speak(self, text, question_id=None, language="en"):
        if self.closed or self.pc.connectionState != "connected":
            raise ValueError("The live avatar connection is not ready. Reconnect and try again.")
        if any(job["status"] in ("queued", "speaking") for job in self.jobs.values()):
            raise ValueError("The avatar is speaking. Wait for it to finish or stop the current speech.")
        self.manager.settings.tts_profile(language)
        job = {"id": uuid.uuid4().hex, "status": "queued", "transport": "webrtc", "question_id": question_id,
               "language": language}
        self.jobs[job["id"]] = job
        self.avatar.put_msg_txt(text, {"job_id": job["id"], "language": language})
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
            session.player = PairedHumanPlayer(session.avatar, event_loop=session.loop)

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

            # aiortc chooses its send codec while applying the remote offer.
            # Preferences set afterwards only reorder the answer, leaving the
            # actual sender on VP8 (with visible quality pumping as it adapts).
            session.pc.addTrack(session.player.audio)
            session.pc.addTrack(session.player.video)
            for transceiver in session.pc.getTransceivers():
                if transceiver.kind == "video":
                    codecs = RTCRtpSender.getCapabilities("video").codecs
                    transceiver.setCodecPreferences([c for c in codecs if c.mimeType == "video/H264"] +
                                                     [c for c in codecs if c.mimeType != "video/H264"])
            await session.pc.setRemoteDescription(RTCSessionDescription(sdp=sdp, type=description_type))
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
