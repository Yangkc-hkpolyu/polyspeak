###############################################################################
#  Copyright (C) 2024 LiveTalking@lipku https://github.com/lipku/LiveTalking
#  email: lipku@foxmail.com
# 
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#  
#       http://www.apache.org/licenses/LICENSE-2.0
# 
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import asyncio
import json
import logging
import os
import threading
import time
from queue import Empty, Full, Queue as ThreadQueue
from typing import Tuple, Dict, Optional, Set, Union
from av.frame import Frame
from av.packet import Packet
from av import AudioFrame
import fractions
import numpy as np

AUDIO_PTIME = 0.020  # 20ms audio packetization
VIDEO_CLOCK_RATE = 90000
VIDEO_PTIME = 0.040  # 1/25fps；wav2lip 每帧对应 2 个 20ms 音频帧（40ms 内容），与 AUDIO_PTIME=0.020 配合维持 2:1 音视同步比例
VIDEO_TIME_BASE = fractions.Fraction(1, VIDEO_CLOCK_RATE)
SAMPLE_RATE = 16000
AUDIO_TIME_BASE = fractions.Fraction(1, SAMPLE_RATE)

def _parse_lt_audio_delay_frames() -> int:
    raw = os.environ.get("LT_AUDIO_DELAY_FRAMES", "0") or "0"
    try:
        v = int(raw.strip())
    except ValueError:
        return 0
    return max(0, v)


def _parse_lt_av_stall_reanchor_ms() -> float:
    """上游 LLM/TTS 卡顿导致音视频帧落后于墙钟 > 该阈值时，重锚 _start 到当前时间，
    避免恢复时帧 burst 造成 A/V 失步。0 = 禁用（保持原有行为）。单位：毫秒。"""
    raw = os.environ.get("LT_AV_STALL_REANCHOR_MS", "0") or "0"
    try:
        v = float(raw.strip())
    except ValueError:
        return 0.0
    return max(0.0, v)


_AUDIO_DELAY_FRAMES = _parse_lt_audio_delay_frames()
_AV_STALL_REANCHOR_S = _parse_lt_av_stall_reanchor_ms() / 1000.0

#from aiortc.contrib.media import MediaPlayer, MediaRelay
#from aiortc.rtcrtpsender import RTCRtpSender
from aiortc import (
    MediaStreamTrack,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
from .logger import logger as mylogger

# run_in_executor 内不能用无限阻塞的 queue.get()：stop() 时 get_nowait 无法唤醒已在 get 中阻塞的线程，会占满会话 executor。
_GET_POLL_TIMEOUT_S = 0.05


class _TrackClosedError(RuntimeError):
    """_closed 已置位后 executor 内退出阻塞 get。"""


class PlayerStreamTrack(MediaStreamTrack):
    """
    A video track that returns an animated flag.
    """

    def __init__(self, player, kind):
        super().__init__()  # don't forget this!
        self.kind = kind
        self._player = player
        self._queue = ThreadQueue(maxsize=100)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_queue: Optional[asyncio.Queue] = None
        self._bridge_task: Optional[asyncio.Task] = None
        self._drop_count = 0
        self._closed = threading.Event()
        self.timelist = [] #记录最近包的时间戳
        self.current_frame_count = 0
        if self.kind == 'video':
            self.framecount = 0
            self.lasttime = time.perf_counter()
            self.totaltime = 0
    
    _start: float
    _timestamp: int

    def _setup_async_queue(self, loop: asyncio.AbstractEventLoop) -> None:
        """小容量 asyncio.Queue + bridge task，用 await put 背压，避免 call_soon_threadsafe 批量爆发。"""
        self._loop = loop
        self._async_queue = asyncio.Queue(maxsize=2)

    def _async_queue_drain_then_sentinel_nowait(self) -> None:
        """仅在 event loop 线程调用；用于 stop() 与 bridge cancel 后投递终止帧。"""
        if self._async_queue is None:
            return
        while True:
            try:
                self._async_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        try:
            self._async_queue.put_nowait((None, None))
        except asyncio.QueueFull:
            pass

    async def _queue_bridge(self) -> None:
        """ThreadQueue -> run_in_executor -> asyncio.Queue；put 满时阻塞，与 recv 消费同步。"""
        loop = self._loop
        aq = self._async_queue
        if loop is None or aq is None:
            return
        while True:
            try:
                item = await loop.run_in_executor(None, self._executor_get_frame)
            except _TrackClosedError:
                while True:
                    try:
                        aq.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                await aq.put((None, None))
                return
            await aq.put(item)

    async def next_timestamp(self) -> Tuple[int, fractions.Fraction]:
        if self.readyState != "live":
            raise Exception

        if self.kind == 'video':
            if hasattr(self, "_timestamp"):
                #self._timestamp = (time.time()-self._start) * VIDEO_CLOCK_RATE
                self._timestamp += int(VIDEO_PTIME * VIDEO_CLOCK_RATE)
                self.current_frame_count += 1
                wait = (
                    self._start
                    + self.current_frame_count * VIDEO_PTIME
                    - time.time()
                )
                # wait = self.timelist[0] + len(self.timelist)*VIDEO_PTIME - time.time()
                if wait>0:
                    await asyncio.sleep(wait)
                elif _AV_STALL_REANCHOR_S > 0 and -wait > _AV_STALL_REANCHOR_S:
                    # 上游 stall 已让该轨落后 > 阈值；重锚 _start 使下一帧回到正常节流，
                    # 避免后续帧 burst 打乱音视频相对节奏。
                    self._start = time.time() - self.current_frame_count * VIDEO_PTIME
                # if len(self.timelist)>=100:
                #     self.timelist.pop(0)
                # self.timelist.append(time.time())
            else:
                self._start = self._player._get_or_set_session_start()
                self._timestamp = 0
                self.timelist.append(self._start)
                mylogger.info('video start:%f', self._start)
            return self._timestamp, VIDEO_TIME_BASE
        else: #audio
            if hasattr(self, "_timestamp"):
                #self._timestamp = (time.time()-self._start) * SAMPLE_RATE
                self._timestamp += int(AUDIO_PTIME * SAMPLE_RATE)
                self.current_frame_count += 1
                wait = (
                    self._start
                    + self.current_frame_count * AUDIO_PTIME
                    + _AUDIO_DELAY_FRAMES * AUDIO_PTIME
                    - time.time()
                )
                # wait = self.timelist[0] + len(self.timelist)*AUDIO_PTIME - time.time()
                if wait > 0:
                    await asyncio.sleep(wait)
                elif _AV_STALL_REANCHOR_S > 0 and -wait > _AV_STALL_REANCHOR_S:
                    # 同 video 路径：上游 stall 导致该轨落后 > 阈值时重锚。
                    self._start = (
                        time.time()
                        - self.current_frame_count * AUDIO_PTIME
                        - _AUDIO_DELAY_FRAMES * AUDIO_PTIME
                    )
                # if len(self.timelist)>=200:
                #     self.timelist.pop(0)
                #     self.timelist.pop(0)
                # self.timelist.append(time.time())
            else:
                self._start = self._player._get_or_set_session_start()
                self._timestamp = 0
                self.timelist.append(self._start)
                mylogger.info('audio start:%f', self._start)
            return self._timestamp, AUDIO_TIME_BASE

    def put_frame_nowait(self, item: tuple) -> bool:
        """
        由 media-player 线程调用。队列满时丢帧并计数。
        """
        try:
            self._queue.put_nowait(item)
            return True
        except Full:
            self._drop_count += 1
            return False

    def _executor_get_frame(self) -> tuple:
        while not self._closed.is_set():
            try:
                return self._queue.get(timeout=_GET_POLL_TIMEOUT_S)
            except Empty:
                continue
        raise _TrackClosedError()

    async def recv(self) -> Union[Frame, Packet]:
        # frame = self.frames[self.counter % 30]            
        self._player._start(self)
        if self._async_queue is not None:
            if self._bridge_task is None and self._loop is not None:
                self._bridge_task = self._loop.create_task(self._queue_bridge())
            frame, eventpoint = await self._async_queue.get()
        else:
            loop = asyncio.get_event_loop()
            try:
                frame, eventpoint = await loop.run_in_executor(
                    None, self._executor_get_frame
                )
            except _TrackClosedError:
                raise Exception("track closed")
        if frame is None:
            self.stop()
            raise Exception("track closed")
        pts, time_base = await self.next_timestamp()
        frame.pts = pts
        frame.time_base = time_base
        if eventpoint and self._player is not None:
            self._player.notify(eventpoint)
        if self.kind == 'video':
            self.totaltime += (time.perf_counter() - self.lasttime)
            self.framecount += 1
            self.lasttime = time.perf_counter()
            if self.framecount==100:
                mylogger.info(f"------actual avg final fps:{self.framecount/self.totaltime:.4f}")
                self.framecount = 0
                self.totaltime=0
        return frame
    
    def stop(self):
        self._closed.set()
        if self._loop is not None and self._async_queue is not None:

            def _cancel_and_sentinel() -> None:
                if self._bridge_task is not None and not self._bridge_task.done():
                    self._bridge_task.cancel()
                self._async_queue_drain_then_sentinel_nowait()

            try:
                self._loop.call_soon_threadsafe(_cancel_and_sentinel)
            except RuntimeError:
                pass
        super().stop()
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except Empty:
                break
        if self._player is not None:
            self._player._stop(self)
            self._player = None

def player_worker_thread(
    quit_event,
    loop,
    container,
    audio_track,
    video_track
):
    container.render(quit_event,loop,audio_track,video_track)

class HumanPlayer:

    def __init__(
        self,
        nerfreal,
        format=None,
        options=None,
        timeout=None,
        loop=False,
        decode=True,
        event_loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.__thread: Optional[threading.Thread] = None
        self.__thread_quit: Optional[threading.Event] = None

        # examine streams
        self.__started: Set[PlayerStreamTrack] = set()
        self.__audio: Optional[PlayerStreamTrack] = None
        self.__video: Optional[PlayerStreamTrack] = None

        self.__audio = PlayerStreamTrack(self, kind="audio")
        self.__video = PlayerStreamTrack(self, kind="video")
        if event_loop is not None:
            self.__audio._setup_async_queue(event_loop)
            self.__video._setup_async_queue(event_loop)

        self.__container = nerfreal
        self._session_start: Optional[float] = None
        self._session_start_lock = threading.Lock()

    def _get_or_set_session_start(self) -> float:
        with self._session_start_lock:
            if self._session_start is None:
                self._session_start = time.time()
            return self._session_start

    def notify(self,eventpoint):
        if self.__container is not None:
            self.__container.notify(eventpoint)

    @property
    def audio(self) -> MediaStreamTrack:
        """
        A :class:`aiortc.MediaStreamTrack` instance if the file contains audio.
        """
        return self.__audio

    @property
    def video(self) -> MediaStreamTrack:
        """
        A :class:`aiortc.MediaStreamTrack` instance if the file contains video.
        """
        return self.__video

    def _start(self, track: PlayerStreamTrack) -> None:
        self.__started.add(track)
        if self.__thread is None:
            self.__log_debug("Starting worker thread")
            self.__thread_quit = threading.Event()
            self.__thread = threading.Thread(
                name="media-player",
                target=player_worker_thread,
                args=(
                    self.__thread_quit,
                    None,
                    self.__container,
                    self.__audio,
                    self.__video                   
                ),
            )
            self.__thread.start()

    def _stop(self, track: PlayerStreamTrack) -> None:
        self.__started.discard(track)

        if not self.__started and self.__thread is not None:
            self.__log_debug("Stopping worker thread")
            self.__thread_quit.set()
            self.__thread.join()
            self.__thread = None

        if not self.__started and self.__container is not None:
            #self.__container.close()
            self.__container = None

    def __log_debug(self, msg: str, *args) -> None:
        mylogger.debug(f"HumanPlayer {msg}", *args)
