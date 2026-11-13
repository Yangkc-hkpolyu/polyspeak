import asyncio
from functools import wraps
from queue import Queue
from threading import Event, Thread
from types import SimpleNamespace

import numpy as np
import pytest

from backend.speaking import live_tts
from backend.speaking.config import Settings


def run_async(test):
    @wraps(test)
    def run(*args, **kwargs):
        return asyncio.run(test(*args, **kwargs))
    return run


def pcm(seconds):
    t = np.arange(round(seconds * 24000)) / 24000
    return (np.sin(t * 2 * np.pi * 220) * 6000).astype('<i2').tobytes()


def adapter():
    events = []
    parent = SimpleNamespace(asr=SimpleNamespace(queue=Queue()), live_event=events.append)
    return live_tts.StreamingTTS(SimpleNamespace(speaking_settings=Settings()), parent), events


def drain(tts):
    out = []
    while not tts.parent.asr.queue.empty():
        out.append(tts.parent.asr.queue.get_nowait())
    return out


def test_speech_bounds_ignore_padding_but_keep_quiet_speech_and_internal_pauses():
    samples = np.concatenate((np.zeros(12 * 320), np.full(4 * 320, .0003),
                              np.zeros(8 * 320), np.full(4 * 320, .02), np.zeros(10 * 320))).astype(np.float32)
    assert live_tts.speech_sample_bounds(samples) == (12 * 320, 28 * 320)
    assert live_tts.speech_sample_bounds(np.zeros(100, np.float32)) == (100, 100)


@run_async
async def test_tts_padding_keeps_audio_and_events_but_cannot_animate_the_mouth(monkeypatch):
    async def stream(_settings, _text, language="en"):
        yield b'\x00\x00' * 5760  # 240 ms leading silence, as found in real TTS
        yield pcm(.64)
        yield b'\x00\x00' * 5760

    monkeypatch.setattr(live_tts, 'stream_tts', stream)
    tts, _events = adapter()
    await tts.synthesize('hello', {'job_id': 'padded'}, 0, Event())
    frames = drain(tts)
    assert frames[0][1] == {'job_id': 'padded', 'status': 'start', 'lip_silent': True}
    assert frames[-1][1] == {'job_id': 'padded', 'status': 'end'}
    audio = np.concatenate([frame for frame, _info in frames[:-1]])
    assert len(audio) == 17920  # All 1.12 seconds retained, including both pads
    assert np.max(np.abs(audio[:3200])) == np.max(np.abs(audio[-3200:])) == 0
    assert np.max(np.abs(audio[4000:14000])) > .1
    assert all(info and info.get('lip_silent') for _, info in frames[:10] + frames[-11:-1])
    assert all(info is None for _, info in frames[14:40])
    assert 200 <= tts.stats['leading_quiet_ms'] <= 240
    assert 200 <= tts.stats['trailing_quiet_ms'] <= 240


@run_async
async def test_cloud_chunk_gap_is_buffered_before_speech_starts(monkeypatch):
    first = asyncio.Event()
    resume = asyncio.Event()
    all_chunks = asyncio.Event()
    complete = asyncio.Event()

    async def stream(_settings, _text, language="en"):
        yield pcm(.32)
        first.set()
        await resume.wait()
        for _ in range(3):
            yield pcm(.32)
        all_chunks.set()
        await complete.wait()

    monkeypatch.setattr(live_tts, 'stream_tts', stream)
    tts, events = adapter()
    task = asyncio.create_task(tts.synthesize('test', {'job_id': 'buffered'}, 0, Event()))
    await asyncio.wait_for(first.wait(), 2)
    assert tts.parent.asr.queue.empty(), 'Do not start a syllable before its complete source audio is ready'
    resume.set()
    await asyncio.wait_for(all_chunks.wait(), 2)
    assert tts.parent.asr.queue.empty(), 'Even a long utterance must not play while source chunks are still pending'
    complete.set()
    await asyncio.wait_for(task, 2)
    frames = drain(tts)
    assert len(frames) == 65  # 1.28 seconds plus the end marker
    assert frames[0][1] == {'job_id': 'buffered', 'status': 'start'}
    assert frames[-1][1] == {'job_id': 'buffered', 'status': 'end'}
    assert all(info is None for _, info in frames[1:-1])
    assert all(np.max(np.abs(samples)) > .1 for samples, _ in frames[:-1])
    assert tts.stats['audio_samples'] == 20480
    assert events[-1]['type'] == 'speech.generated'


@run_async
async def test_short_utterance_flushes_without_waiting_for_full_reserve(monkeypatch):
    async def stream(_settings, _text, language="en"):
        yield pcm(.08)

    monkeypatch.setattr(live_tts, 'stream_tts', stream)
    tts, _events = adapter()
    await asyncio.wait_for(tts.synthesize('yes', {'job_id': 'short'}, 0, Event()), 2)
    frames = drain(tts)
    assert len(frames) == 5
    assert frames[0][1]['status'] == 'start'
    assert frames[-1][1]['status'] == 'end'
    assert tts.stats['audio_samples'] == 1280


@run_async
async def test_avatar_warmup_finishes_before_any_speech_pcm_is_published(monkeypatch):
    async def stream(_settings, _text, language="en"):
        yield pcm(.08)

    monkeypatch.setattr(live_tts, 'stream_tts', stream)
    tts, _events = adapter()
    started, proceed = Event(), Event()
    def prepare():
        started.set()
        assert proceed.wait(2)
    tts.parent.prepare_speech = prepare
    task = asyncio.create_task(tts.synthesize('yes', {'job_id': 'warm'}, 0, Event()))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        assert tts.parent.asr.queue.empty()
    finally:
        proceed.set()
    await task
    assert len(drain(tts)) == 5


@run_async
async def test_interrupt_during_priming_does_not_play_stale_audio(monkeypatch):
    first = asyncio.Event()

    async def stream(_settings, text, language="en"):
        yield pcm(.08)
        if text == 'old':
            first.set()
            await asyncio.Event().wait()

    monkeypatch.setattr(live_tts, 'stream_tts', stream)
    tts, events = adapter()
    task = asyncio.create_task(tts.synthesize('old', {'job_id': 'old'}, 0, Event()))
    await asyncio.wait_for(first.wait(), 2)
    tts.flush_talk()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert tts.parent.asr.queue.empty()
    assert not events
    await tts.synthesize('new', {'job_id': 'new'}, tts.epoch, Event())
    assert all(info is None or info['job_id'] == 'new' for _, info in drain(tts))


def test_interrupt_while_input_queue_is_full_cannot_enqueue_old_audio(monkeypatch):
    waiting = Event()

    class ObservedQueue(Queue):
        def put_nowait(self, item):
            waiting.set()
            return super().put_nowait(item)

    async def stream(_settings, _text, language="en"):
        yield pcm(.08)

    monkeypatch.setattr(live_tts, 'stream_tts', stream)
    tts, events = adapter()
    tts.parent.asr.queue = ObservedQueue(maxsize=1)
    tts.parent.asr.queue.put(('already queued', None))
    cancelled = Event()

    def produce():
        try:
            asyncio.run(tts.synthesize('old', {'job_id': 'old'}, 0, Event()))
        except asyncio.CancelledError:
            cancelled.set()

    worker = Thread(target=produce)
    worker.start()
    assert waiting.wait(2)
    tts.flush_talk()
    tts.parent.asr.queue.get_nowait()  # reset frees space while cancellation is pending
    worker.join(timeout=2)
    assert not worker.is_alive() and cancelled.is_set()
    assert tts.parent.asr.queue.empty()
    assert not events
