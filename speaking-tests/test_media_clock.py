import asyncio
from threading import local
from types import SimpleNamespace

import av

from backend.speaking.media_clock import PairedMediaClock, PairedStreamTrack


def test_interrupt_keeps_two_audio_chunks_aligned_with_their_video_frame():
    now = [100.0]
    clock = PairedMediaClock(lambda: now[0])
    assert clock.stamp('video', 0)[0] == 0
    assert clock.stamp('audio', 0)[0] == 0
    assert clock.stamp('audio', 0)[0] == 320
    clock.delay(0)
    clock.delivered(.02)
    # Producer was 800 ms ahead; an interruption discards this buffered content.
    for _ in range(20):
        clock.stamp('video', 0)
        clock.stamp('audio', 0)
        clock.stamp('audio', 0)
    now[0] += .16
    for epoch in range(1, 8):
        video = clock.stamp('video', epoch)
        a = clock.stamp('audio', epoch)
        b = clock.stamp('audio', epoch)
        assert video[0] * video[1] == a[0] * a[1]
        assert float(b[0] * b[1] - a[0] * a[1]) == .02
        clock.delivered(float(b[0] * b[1]))
        now[0] += .08


def test_receiver_rejects_old_epoch_even_when_bridge_already_dequeued_it():
    async def exercise():
        avatar = SimpleNamespace(_output_epoch=local(), _stream_epoch=0)
        avatar._output_epoch.value = 0
        player = SimpleNamespace(_start=lambda _: None, notify=lambda _: None)
        clock = PairedMediaClock()
        track = PairedStreamTrack(player, 'video', avatar, clock)
        track._async_queue = asyncio.Queue()
        old = av.VideoFrame(16, 16, 'yuv420p')
        old.pts, old.time_base = clock.stamp('video', 0)
        await track._async_queue.put((old, None, 0))
        avatar._stream_epoch = 1
        new = av.VideoFrame(16, 16, 'yuv420p')
        new.pts, new.time_base = clock.stamp('video', 1)
        await track._async_queue.put((new, None, 1))
        assert await track.recv() is new
    asyncio.run(exercise())
