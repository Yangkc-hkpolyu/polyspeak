import asyncio
import json
import wave

import numpy as np
import pytest

from backend.speaking.voice_coach.metrics import measure_recording
from backend.speaking.voice_coach.service import VoiceCoach
from backend.speaking.voice_coach.worker import normalize_metrics, validate_output
from test_protocol import ctx, start, capture, submit


@pytest.fixture
def isolated_ctx(ctx, tmp_path):
    ctx[4].state.voice_coach.root = tmp_path / "uninstalled-model"
    return ctx


def audio(path, sections):
    data = np.concatenate([np.sin(np.arange(int(seconds * 16000)) * 2 * np.pi * 220 / 16000) * level for seconds, level in sections])
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1); stream.setsampwidth(2); stream.setframerate(16000)
        stream.writeframes((data * 32767).astype("<i2").tobytes())


def metric():
    return normalize_metrics({"status": "ok", "detection_method": "energy_estimate", "speaking_span_seconds": 10,
        "transcript_word_count": 20, "words_per_minute": 120, "pause_count": 0, "pauses": [],
        "recording": {"peak_dbfs": -10, "clipped_fraction": 0}})


def test_measures_inner_pauses_without_outer_silence(tmp_path):
    path = tmp_path / "sample.wav"
    audio(path, [(.6, 0), (.4, .2), (.8, 0), (.4, .2), (.6, 0)])
    result = measure_recording(path, "This is my answer.")
    assert result["pause_count"] == 1
    assert result["pauses"][0] == {"start_seconds": 1, "end_seconds": 1.8, "duration_seconds": .8}
    assert result["speaking_span_seconds"] == 1.6
    assert result["words_per_minute"] == 150
    assert result["pronunciation_assessed"] is False


def test_silence_and_missing_transcript_do_not_invent_pace(tmp_path):
    path = tmp_path / "sample.wav"
    audio(path, [(1, 0)])
    result = measure_recording(path, "An unreliable transcript")
    assert result["status"] == "insufficient_audio"
    assert result["words_per_minute"] is result["pause_count"] is None
    audio(path, [(1, .2)])
    assert measure_recording(path, "")["words_per_minute"] is None


def test_missing_adapter_cannot_report_finetuned_success(tmp_path):
    service = VoiceCoach(tmp_path / "models", tmp_path)
    result = asyncio.run(service.advise(metric()))
    assert result["status"] == "unavailable" and result["advice"] is None
    assert result["reason"] == "adapter_missing"


@pytest.mark.parametrize("text", ["Your pronunciation is clear.", "The pace is 150 words per minute.", "You have 3 pauses.", "The recorded level is low; try moving the microphone closer."])
def test_preserves_contributor_grounding_checks(text):
    assert not validate_output(text, metric())


def test_worker_gets_only_metrics_and_no_gpu(monkeypatch, tmp_path):
    service = VoiceCoach(tmp_path, tmp_path)
    monkeypatch.setattr(service, "status", lambda: {"ready": True})
    captured = {}
    class Process:
        returncode = 0
        async def communicate(self, data):
            captured["payload"] = json.loads(data)
            return json.dumps({"status": "ok", "advice": "The estimated pace is 120 words per minute over 10 seconds."}).encode(), None
        async def wait(self): pass
    async def spawn(*args, **kwargs):
        captured.update(kwargs)
        return Process()
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    result = asyncio.run(service.advise({**metric(), "transcript": "private answer", "audio": "private audio"}))
    assert result["status"] == "ok"
    assert "transcript" not in captured["payload"] and "audio" not in captured["payload"]
    assert captured["env"]["CUDA_VISIBLE_DEVICES"] == "-1"
    assert not service.processes


def test_timeout_terminates_worker(monkeypatch, tmp_path):
    service = VoiceCoach(tmp_path, tmp_path, timeout=.01)
    monkeypatch.setattr(service, "status", lambda: {"ready": True})
    class Process:
        returncode = None
        killed = False
        async def communicate(self, data): await asyncio.sleep(10)
        def kill(self): self.killed = True; self.returncode = -1
        async def wait(self): pass
    process = Process()
    async def spawn(*args, **kwargs): return process
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    assert asyncio.run(service.advise(metric()))["reason"] == "timeout"
    assert process.killed and not service.processes


def test_review_is_post_session_saved_and_exported(isolated_ctx):
    ctx = isolated_ctx
    session = start(ctx, execution="demo")
    client = ctx[0]
    recording = capture(ctx, session).json()
    session = submit(ctx, session, audio_id=recording["id"]).json()
    turn = session["turns"][0]
    url = f"/api/speaking/sessions/{session['id']}/turns/{turn['id']}/voice-coach"
    assert client.post(url).status_code == 409
    finished = client.post(f"/api/speaking/sessions/{session['id']}/finish").json()
    response = client.post(url)
    assert response.status_code == 200, response.text
    assert response.json()["advice"]["reason"] == "adapter_missing"
    after = client.get(f"/api/speaking/sessions/{session['id']}").json()
    assert after["report"] == finished["report"]
    assert after["turns"][0]["voice_coach"] == response.json()
    exported = client.get(f"/api/speaking/sessions/{session['id']}/export").json()
    assert exported["turns"][0]["voice_coach"] == response.json()
    assert client.post(url.replace(turn["id"], "missing")).status_code == 404


def test_typed_answers_and_foreign_turns_cannot_get_audio_review(isolated_ctx):
    ctx = isolated_ctx
    session = start(ctx, execution="demo")
    session = submit(ctx, session, answer="My typed answer.").json()
    client = ctx[0]
    client.post(f"/api/speaking/sessions/{session['id']}/finish")
    url = f"/api/speaking/sessions/{session['id']}/turns/{session['turns'][0]['id']}/voice-coach"
    assert client.post(url).status_code == 409
    other = start(ctx, execution="demo")
    assert client.post(url.replace(session["id"], other["id"])).status_code == 409
