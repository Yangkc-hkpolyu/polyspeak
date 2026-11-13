"""Keep paired audio/video timestamps together across interrupted queue clears."""
import asyncio
from fractions import Fraction
import math
import threading
import time

from aiortc.mediastreams import MediaStreamError

from .vendor.livetalking.webrtc import HumanPlayer, PlayerStreamTrack, _TrackClosedError


class PairedMediaClock:
    def __init__(self, now=time.monotonic):
        self.now = now
        self.start = None
        self.epoch = None
        self.next_pair = 0
        self.pair = 0
        self.audio_half = 0
        self.last_delivered = -0.04
        self.lock = threading.Lock()

    def stamp(self, kind, epoch):
        # One renderer thread publishes one video frame, then two PCM chunks.
        with self.lock:
            if kind == "video":
                if epoch != self.epoch:
                    elapsed = 0 if self.start is None else self.now() - self.start
                    self.next_pair = max(math.ceil(elapsed * 25), math.floor(self.last_delivered * 25) + 1)
                    self.epoch = epoch
                self.pair = self.next_pair
                self.next_pair += 1
                self.audio_half = 0
                return self.pair * 3600, Fraction(1, 90000)
            pts = (self.pair * 2 + self.audio_half) * 320
            self.audio_half += 1
            return pts, Fraction(1, 16000)

    def delay(self, media_time):
        with self.lock:
            if self.start is None:
                self.start = self.now() - media_time
            return max(0, self.start + media_time - self.now())

    def delivered(self, media_time):
        with self.lock:
            self.last_delivered = max(self.last_delivered, media_time)


class PairedStreamTrack(PlayerStreamTrack):
    def __init__(self, player, kind, avatar, clock):
        super().__init__(player, kind)
        self.avatar, self.clock = avatar, clock

    def put_frame_nowait(self, item):
        frame, event = item
        epoch = getattr(self.avatar._output_epoch, "value", self.avatar._stream_epoch)
        frame.pts, frame.time_base = self.clock.stamp(self.kind, epoch)
        return super().put_frame_nowait((frame, event, epoch))

    async def recv(self):
        self._player._start(self)
        if self._bridge_task is None and self._loop is not None:
            self._bridge_task = self._loop.create_task(self._queue_bridge())
        while self.readyState == "live":
            try:
                item = await self._async_queue.get() if self._async_queue is not None else await asyncio.get_running_loop().run_in_executor(None, self._executor_get_frame)
            except _TrackClosedError:
                raise MediaStreamError
            frame, event = item[:2]
            if frame is None:
                raise MediaStreamError
            epoch = item[2]
            if epoch != self.avatar._stream_epoch:
                continue
            media_time = float(frame.pts * frame.time_base)
            await asyncio.sleep(self.clock.delay(media_time))
            # An interruption may have happened while waiting for this frame.
            if epoch != self.avatar._stream_epoch:
                continue
            self.clock.delivered(media_time)
            if event:
                self._player.notify(event)
            return frame
        raise MediaStreamError


class PairedHumanPlayer(HumanPlayer):
    def __init__(self, avatar, event_loop):
        super().__init__(avatar)
        clock = PairedMediaClock()
        # Reuse the vendored player's worker, shutdown and event delivery.
        self._HumanPlayer__audio = PairedStreamTrack(self, "audio", avatar, clock)
        self._HumanPlayer__video = PairedStreamTrack(self, "video", avatar, clock)
        self.audio._setup_async_queue(event_loop)
        self.video._setup_async_queue(event_loop)
