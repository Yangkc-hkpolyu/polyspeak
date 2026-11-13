"""Collect cloud PCM, then feed LiveTalking in order like PolyInterview EdgeTTS."""
import asyncio
from queue import Empty, Full, Queue
import threading
import time

import av
import numpy as np

from .realtime_cloud import stream_tts


def speech_sample_bounds(samples, chunk=320, quiet_rms=0.0002):
    """Find the utterance's audible extent without trimming or changing PCM.

    Only outer padding is suppressed visually. Quiet consonants and pauses
    inside the utterance retain the model's normal coarticulation.
    """
    if not len(samples):
        return 0, 0
    padded = np.pad(samples, (0, (-len(samples)) % chunk))
    energy = np.sqrt(np.mean(padded.reshape(-1, chunk) ** 2, axis=1))
    active = np.flatnonzero(energy >= quiet_rms)
    if not len(active):
        return len(samples), len(samples)
    return int(active[0]) * chunk, min(len(samples), (int(active[-1]) + 1) * chunk)


class StreamingTTS:
    def __init__(self, opt, parent):
        self.settings, self.parent = opt.speaking_settings, parent
        self.messages = Queue(maxsize=4)
        self.epoch = 0
        self.loop = self.active_task = None
        self.thread = None
        self._queue_lock = threading.Lock()
        self.playback_started = False
        self.stats = {}

    def put_msg_txt(self, text, datainfo=None):
        self.messages.put_nowait((text, dict(datainfo or {}), self.epoch))

    def flush_talk(self):
        with self._queue_lock:
            self.epoch += 1
            self.playback_started = False
        while True:
            try:
                self.messages.get_nowait()
            except Empty:
                break
        if self.loop and self.active_task:
            try:
                self.loop.call_soon_threadsafe(self.active_task.cancel)
            except RuntimeError:
                pass

    def render(self, quit_event):
        if self.thread is None:
            self.thread = threading.Thread(target=self.process, args=(quit_event,), daemon=True, name="speaking-stream-tts")
            self.thread.start()

    def process(self, quit_event):
        while not quit_event.is_set():
            try:
                text, metadata, epoch = self.messages.get(timeout=0.2)
            except Empty:
                continue
            try:
                asyncio.run(self.synthesize(text, metadata, epoch, quit_event))
            except asyncio.CancelledError:
                pass
            except Exception:
                self.parent.live_event({"type": "speech.error", "job_id": metadata.get("job_id"),
                                        "message": "Live speech synthesis could not be completed. Check the selected voice and connection, then try again."})
            finally:
                self.loop = self.active_task = None

    async def synthesize(self, text, metadata, epoch, quit_event):
        self.loop, self.active_task = asyncio.get_running_loop(), asyncio.current_task()
        converter = av.AudioResampler(format="s16", layout="mono", rate=16000)
        buffered = np.empty(0, np.float32)
        started = False
        began = time.perf_counter()
        language = metadata.get("language", "en")
        stats = {**self.settings.tts_profile(language), "buffering": "complete_utterance",
                 "source_chunks": 0, "audio_samples": 0, "startup_ms": None,
                 "max_source_chunk_gap_ms": 0.0, "synthesis_complete": False}
        self.stats = stats
        previous_chunk = None
        self.playback_started = False

        def put(chunk, info=None):
            while True:
                # A blocking put could succeed after flush freed the queue and
                # inject an obsolete syllable. Make epoch check + enqueue atomic.
                with self._queue_lock:
                    if quit_event.is_set() or epoch != self.epoch:
                        raise asyncio.CancelledError()
                    try:
                        self.parent.asr.queue.put_nowait((chunk, info))
                        return
                    except Full:
                        pass
                quit_event.wait(0.01)

        async for pcm in stream_tts(self.settings, text, language=language):
            if epoch != self.epoch or quit_event.is_set():
                raise asyncio.CancelledError()
            arrived = time.perf_counter()
            if previous_chunk is not None:
                stats["max_source_chunk_gap_ms"] = max(stats["max_source_chunk_gap_ms"], (arrived - previous_chunk) * 1000)
            previous_chunk = arrived
            stats["source_chunks"] += 1
            frame = av.AudioFrame.from_ndarray(np.frombuffer(pcm, dtype="<i2").reshape(1, -1), format="s16", layout="mono")
            frame.sample_rate = 24000
            for converted in converter.resample(frame):
                samples = converted.to_ndarray().reshape(-1).astype(np.float32) / 32768.0
                buffered = np.concatenate((buffered, samples))
            # The original EdgeTTS adapter collects the complete utterance before
            # publishing it. Keep that boundary: a network gap must never become
            # a synthetic pause halfway through a word. Video remains live WebRTC.
        for converted in converter.resample(None):
            buffered = np.concatenate((buffered, converted.to_ndarray().reshape(-1).astype(np.float32) / 32768.0))
        speech_begin, speech_end = speech_sample_bounds(buffered)
        stats["leading_quiet_ms"] = speech_begin / 16
        stats["trailing_quiet_ms"] = (len(buffered) - speech_end) / 16
        prepare = getattr(self.parent, "prepare_speech", None)
        if prepare:
            await asyncio.to_thread(prepare)
        offset = 0

        def frame_info():
            info = {**metadata, "status": "start"} if not started else {}
            # The vendor treats all supplied PCM as speech, even TTS padding.
            # Mark only outer silence so future mel context cannot open the
            # mouth before the matching audio actually contains speech.
            if offset < speech_begin or offset >= speech_end:
                info["lip_silent"] = True
            return info or None

        while len(buffered) >= 320:
            put(buffered[:320].copy(), frame_info())
            if not started:
                stats["startup_ms"] = (time.perf_counter() - began) * 1000
                self.playback_started = True
            started = True
            stats["audio_samples"] += 320
            offset += 320
            buffered = buffered[320:]
        if len(buffered):
            put(np.pad(buffered, (0, 320 - len(buffered))), frame_info())
            if not started:
                stats["startup_ms"] = (time.perf_counter() - began) * 1000
                self.playback_started = True
            started = True
            stats["audio_samples"] += len(buffered)
        if not started:
            raise RuntimeError("No streaming speech returned")
        put(np.zeros(320, np.float32), {**metadata, "status": "end"})
        stats["synthesis_complete"] = True
        self.parent.live_event({"type": "speech.generated", "job_id": metadata.get("job_id")})
