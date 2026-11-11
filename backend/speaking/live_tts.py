"""Hosted streaming PCM adapter for the original LiveTalking TTS queue boundary."""
import asyncio
from queue import Empty, Full, Queue
import threading

import av
import numpy as np

from .realtime_cloud import stream_tts


class StreamingTTS:
    def __init__(self, opt, parent):
        self.settings, self.parent = opt.speaking_settings, parent
        self.messages = Queue(maxsize=4)
        self.epoch = 0
        self.loop = self.active_task = None
        self.thread = None

    def put_msg_txt(self, text, datainfo=None):
        self.messages.put_nowait((text, dict(datainfo or {}), self.epoch))

    def flush_talk(self):
        self.epoch += 1
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
                                        "message": "实时语音合成未完成，请检查模型权限或重试。"})
            finally:
                self.loop = self.active_task = None

    async def synthesize(self, text, metadata, epoch, quit_event):
        self.loop, self.active_task = asyncio.get_running_loop(), asyncio.current_task()
        converter = av.AudioResampler(format="s16", layout="mono", rate=16000)
        buffered = np.empty(0, np.float32)
        started = False

        def put(chunk, info=None):
            while not quit_event.is_set() and epoch == self.epoch:
                try:
                    self.parent.asr.queue.put((chunk, info), timeout=0.05)
                    return
                except Full:
                    continue
            raise asyncio.CancelledError()

        async for pcm in stream_tts(self.settings, text):
            if epoch != self.epoch or quit_event.is_set():
                raise asyncio.CancelledError()
            frame = av.AudioFrame.from_ndarray(np.frombuffer(pcm, dtype="<i2").reshape(1, -1), format="s16", layout="mono")
            frame.sample_rate = 24000
            for converted in converter.resample(frame):
                samples = converted.to_ndarray().reshape(-1).astype(np.float32) / 32768.0
                buffered = np.concatenate((buffered, samples))
            while len(buffered) >= 320:
                info = {**metadata, "status": "start"} if not started else None
                put(buffered[:320].copy(), info)
                started = True
                buffered = buffered[320:]
        for converted in converter.resample(None):
            buffered = np.concatenate((buffered, converted.to_ndarray().reshape(-1).astype(np.float32) / 32768.0))
        while len(buffered) >= 320:
            put(buffered[:320].copy(), {**metadata, "status": "start"} if not started else None)
            started = True
            buffered = buffered[320:]
        if len(buffered):
            put(np.pad(buffered, (0, 320 - len(buffered))), {**metadata, "status": "start"} if not started else None)
            started = True
        if not started:
            raise RuntimeError("No streaming speech returned")
        put(np.zeros(320, np.float32), {**metadata, "status": "end"})
        self.parent.live_event({"type": "speech.generated", "job_id": metadata.get("job_id")})
