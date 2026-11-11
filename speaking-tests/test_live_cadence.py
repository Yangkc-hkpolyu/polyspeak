from queue import Queue
from threading import Event, Thread, local
from types import SimpleNamespace
import time

import numpy as np

from backend.speaking.live_avatar import (
    EpochOutputTrack, EpochResultQueue, OrderedBatchScheduler,
    SpeakingLipReal, media_reserve_seconds,
)
from backend.speaking.vendor.livetalking.gpu_inference_scheduler import InferenceRequest
from backend.speaking.vendor.livetalking.lipreal import LipReal


def counters():
    return dict(gpu_batches=0, cancelled_gpu_batches=0, gpu_wait_seconds=0.0,
                max_gpu_wait_seconds=0.0, cancelled_output_frames=0)


class DeferredScheduler:
    def __init__(self):
        self.requests = Queue()

    def submit(self, request):
        self.requests.put(request)


def request(result_queue):
    return InferenceRequest("cpu", 1, np.zeros((1, 1, 80, 16)),
                            np.zeros((1, 6, 2, 2)), [], [0], result_queue)


def test_silence_cannot_overtake_a_deferred_speech_batch():
    delegate, output, stats = DeferredScheduler(), Queue(), counters()
    scheduler = OrderedBatchScheduler(delegate, lambda: False, lambda: 0, lambda: 0, stats)
    asr = SimpleNamespace(feat_queue=Queue(), output_queue=Queue(), chunk=320)
    for label, kind in (("speech", 0), ("silence", 1)):
        asr.feat_queue.put(np.zeros((1, 80, 16), np.float32))
        for _ in range(2):
            asr.output_queue.put((np.zeros(320), kind, {"label": label}))
    avatar = SimpleNamespace(batch_size=1, asr=asr, res_frame_queue=output,
        _infer_index=0, _mirror_index=lambda index: index,
        _face_input_cache=np.zeros((2, 6, 2, 2)), _device_id="cpu",
        opt=SimpleNamespace(sessionid=1), _scheduler=scheduler)
    worker = Thread(target=LipReal._drain_inference_batches, args=(avatar,))
    worker.start()
    pending = delegate.requests.get(timeout=1)
    assert output.empty()
    pending.result_queue.put([(None, 0, pending.audio_frames)])
    worker.join(timeout=1)
    assert not worker.is_alive()
    assert output.get_nowait()[0][2][0][2]["label"] == "speech"
    assert output.get_nowait()[2][0][2]["label"] == "silence"


def test_stop_and_late_cancelled_results_do_not_leak_into_a_new_batch():
    delegate, output, stats, stopped = DeferredScheduler(), Queue(), counters(), Event()
    epoch = [0]
    scheduler = OrderedBatchScheduler(delegate, stopped.is_set, lambda: epoch[0], lambda: epoch[0], stats)
    worker = Thread(target=scheduler.submit, args=(request(output),))
    worker.start()
    old = delegate.requests.get(timeout=1)
    epoch[0] += 1
    worker.join(timeout=0.3)
    assert not worker.is_alive()
    old.result_queue.put("obsolete")
    assert output.empty()
    worker = Thread(target=scheduler.submit, args=(request(output),))
    worker.start()
    current = delegate.requests.get(timeout=1)
    current.result_queue.put("current")
    worker.join(timeout=1)
    assert output.get_nowait() == "current"
    worker = Thread(target=scheduler.submit, args=(request(output),))
    worker.start()
    delegate.requests.get(timeout=1)
    stopped.set()
    worker.join(timeout=0.3)
    assert not worker.is_alive() and output.empty()
    assert stats["cancelled_gpu_batches"] == 2


def test_explicit_interrupt_suppresses_only_obsolete_output_frames():
    avatar = SimpleNamespace(_stream_epoch=0, _output_epoch=local(), stats=counters())
    results = EpochResultQueue(2, lambda: avatar._stream_epoch, avatar._output_epoch)
    sent = []
    track = EpochOutputTrack(SimpleNamespace(put_frame_nowait=lambda item: sent.append(item) or True), avatar)
    results.put(["old batch"])
    results.get()
    avatar._stream_epoch = 1
    assert not track.put_frame_nowait("old audio")
    results.put(["new batch"])
    results.get()
    assert track.put_frame_nowait("new audio")
    assert sent == ["new audio"] and avatar.stats["cancelled_output_frames"] == 1


def test_render_resumes_with_a_batch_of_playback_reserve_and_stops_promptly():
    audio, video = SimpleNamespace(_queue=Queue()), SimpleNamespace(_queue=Queue())
    for _ in range(40):
        audio._queue.put(None)
    for _ in range(20):
        video._queue.put(None)
    assert media_reserve_seconds(audio, video) == 0.8
    avatar = SpeakingLipReal.__new__(SpeakingLipReal)
    avatar.owner = SimpleNamespace(closed=False)
    avatar.batch_size = 8
    avatar._stream_epoch = avatar._render_epoch = 0
    avatar._output_epoch = local()
    avatar._flush_requested, avatar._producer_wake = Event(), Event()
    avatar.stats = dict(max_media_reserve_seconds=0.0, producer_wait_seconds=0.0)
    avatar.init_customindex = lambda: None
    avatar.tts = SimpleNamespace(render=lambda quit_event: None)
    avatar._pending_video_frames = lambda: 0
    avatar._drain_inference_batches = lambda: None
    avatar.process_frames = lambda quit_event, *args: quit_event.wait()
    quit_event, observed = Event(), []
    def produce():
        observed.append(media_reserve_seconds(audio, video))
        quit_event.set()
    avatar.asr = SimpleNamespace(run_step=produce)
    def playback():
        while not quit_event.wait(0.04):
            for _ in range(2):
                if not audio._queue.empty():
                    audio._queue.get_nowait()
            if not video._queue.empty():
                video._queue.get_nowait()
    consumer = Thread(target=playback)
    consumer.start()
    started = time.monotonic()
    avatar.render(quit_event, audio_track=audio, video_track=video)
    consumer.join(timeout=1)
    assert 0.32 <= observed[0] <= 0.48
    assert avatar.stats["producer_wait_seconds"] > 0
    assert time.monotonic() - started < 1


def test_source_underflows_count_only_between_consumed_speech_markers():
    avatar = SpeakingLipReal.__new__(SpeakingLipReal)
    avatar._active_audio_job = None
    avatar.stats = dict(audio_input_frames=0, speech_starts=0, speech_ends=0,
                        audio_input_silence_frames_during_speech=0, source_underrun_frames=0)
    frames = iter([(None, 1, None), (None, 0, {"status": "start", "job_id": "one"}),
                   (None, 1, None), (None, 0, {"status": "end", "job_id": "one"}),
                   (None, 1, None)])
    avatar._source_audio_frame = lambda: next(frames)
    for _ in range(5):
        avatar._get_audio_frame()
    assert avatar.stats["source_underrun_frames"] == 1
    assert avatar.stats["speech_starts"] == avatar.stats["speech_ends"] == 1


def test_quiet_tts_padding_uses_idle_frames_without_changing_audio_or_counting_an_underrun():
    avatar = SpeakingLipReal.__new__(SpeakingLipReal)
    avatar._active_audio_job = None
    avatar.stats = dict(audio_input_frames=0, speech_starts=0, speech_ends=0,
                        audio_input_silence_frames_during_speech=0, source_underrun_frames=0)
    quiet = np.zeros(320, np.float32)
    spoken = np.full(320, .001, np.float32)
    frames = iter([(quiet, 0, {"status": "start", "job_id": "one", "lip_silent": True}),
                   (spoken, 0, None), (quiet, 0, {"lip_silent": True}),
                   (quiet, 0, {"status": "end", "job_id": "one"})])
    avatar._source_audio_frame = lambda: next(frames)
    output = [avatar._get_audio_frame() for _ in range(4)]
    assert [kind for _, kind, _ in output] == [1, 0, 1, 1]
    assert output[0][0] is quiet and output[1][0] is spoken
    assert avatar.stats["source_underrun_frames"] == 0
    assert avatar.stats["quiet_lip_frames"] == 3
    assert avatar.stats["speech_starts"] == avatar.stats["speech_ends"] == 1
