from dataclasses import replace
from io import BytesIO
import json
import re
import wave
import pytest
from fastapi.testclient import TestClient

from backend.speaking.app import create_app
from backend.speaking.bank import get_set
from backend.speaking.config import Settings
from backend.speaking.feedback import DIMENSIONS, normalize_feedback
from backend.speaking.provider import ProviderError


def wav(seconds=1):
    data = BytesIO()
    with wave.open(data, "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
        f.writeframes(b"\x00\x00" * int(16000 * seconds))
    return data.getvalue()


class FakeProvider:
    def __init__(self):
        self.calls, self.fail_report = [], False
    async def complete(self, _system, data, **_kwargs):
        self.calls.append(data)
        if data["task"] in ("adaptive", "coach_followup"):
            return {"question": "How could that affect the wider community, and why?"}
        if data["task"] == "assessment_features":
            return {"features": {key: {"score": 6, "quote": data["answer"][:10], "justification": "Based on the actual words.", "suggestion": "Explain the reason in more detail."} for key in data["definitions"]}}
        if data["task"] == "assessment_aspects":
            return {"aspects": {key: {"score": 6, "justification": "Based on the submitted feature evidence."} for key in DIMENSIONS}}
        if data["task"] == "answer_polishing":
            return {"corrections": []}
        if data["task"] == "feedback":
            if self.fail_report:
                raise ProviderError("Temporary feedback failure")
            turn = next(x for x in data["turns"] if x["answer"])
            return {"summary": "A useful example.", "dimensions": [{"key": key, "score": 6, "comment": "Based on the submitted words."} for key in DIMENSIONS], "strengths": ["Clear point."], "improvements": ["Develop the reason."], "next_steps": ["Try one specific example."], "examples": [{"turn_id": turn["id"], "quote": turn["answer"][:10], "suggestion": "Add a reason based on your own experience.", "improved": ""}, {"turn_id": turn["id"], "quote": "I earned a million dollars.", "suggestion": "Quotes not found in the answer must be removed."}]}
        return {"ok": True}


class FakeSpeech:
    fail = False
    async def transcribe(self, _content, _language):
        if self.fail:
            raise ProviderError("ASR unavailable")
        return "I learned to repair a bicycle with my brother. It helped me travel to class."


@pytest.fixture
def ctx(tmp_path):
    provider, speech = FakeProvider(), FakeSpeech()
    clock = [1000.0]
    settings = replace(Settings(), api_key="server-only-test-key", runtime=tmp_path, model_path=tmp_path / "missing.pth")
    app = create_app(settings, provider, speech, clock=lambda: clock[0])
    with TestClient(app) as client:
        yield client, provider, speech, clock, app


def start(ctx, **values):
    client = ctx[0]
    response = client.post("/api/speaking/sessions", json={"exam": "ielts", "set_id": "ielts-learning", "mode": "coach", "section": "part1", **values})
    assert response.status_code == 200, response.text
    return response.json()


def submit(ctx, session, **values):
    return ctx[0].post(f"/api/speaking/sessions/{session['id']}/answers", json={"question_id": session["pending_question_id"], "answer": "I learned to repair a bicycle with my brother.", **values})


def capture(ctx, session, seconds=1):
    client, _, _, clock, _ = ctx
    base = f"/api/speaking/sessions/{session['id']}"
    ready = client.post(base + "/ready", json={"question_id": session["pending_question_id"]}).json()
    clock[0] += ready["current_question"]["prepare_seconds"]
    client.post(base + "/begin-answer", json={"question_id": session["pending_question_id"]})
    return client.post(base + "/capture", data={"question_id": session["pending_question_id"]}, files={"audio": ("answer.wav", wav(seconds), "audio/wav")})


def test_toefl_mock_has_seven_repeats_four_fixed_interviews_and_hides_targets(ctx):
    session = start(ctx, exam="toefl", set_id="toefl-makerspace", mode="mock", section="full")
    planned = get_set("toefl-makerspace")["questions"]
    assert session["total_questions"] == 11
    assert "plan" not in session and "recordings" not in session
    stages = []
    for i in range(11):
        q = session["current_question"]
        stages.append(q["stage"])
        if i < 7:
            assert planned[i]["text"] not in json.dumps(session)
        else:
            assert planned[i]["text"] not in json.dumps(session)
            assert q["answer_seconds"] == 45
        audio = capture(ctx, session)
        assert audio.status_code == 200, audio.text
        ready = ctx[0].get(f"/api/speaking/sessions/{session['id']}").json()
        if i >= 7:
            assert ready["current_question"]["text"] == planned[i]["text"]
        response = submit(ctx, session, audio_id=audio.json()["id"], answer="THIS CLIENT TEXT MUST NOT BE GRADED")
        assert response.status_code == 200, response.text
        session = response.json()
    assert stages == ["repeat"] * 7 + ["interview"] * 4
    assert session["status"] == "completed"
    assert not any(x["task"] in ("adaptive", "coach_followup") for x in ctx[1].calls)
    assert "THIS CLIENT TEXT" not in str(session["turns"])
    assert session["turns"][0]["repetition"]["target"] == planned[0]["text"]
    assert session["turns"][0]["pronunciation"]["status"] == "not_configured"


def test_ielts_long_turn_preparation_is_not_reset_or_skipped_in_mock(ctx):
    session = start(ctx, mode="mock", section="part2")
    client, _, _, clock, _ = ctx
    path = f"/api/speaking/sessions/{session['id']}"
    body = {"question_id": session["pending_question_id"]}
    first = client.post(path + "/ready", json=body).json()
    assert first["current_question"]["card"] and not session["current_question"]["card"]
    assert first["current_question"]["prepare_seconds"] == 60
    assert first["current_question"]["answer_seconds"] == 120
    assert client.post(path + "/begin-answer", json=body).status_code == 422
    clock[0] += 20
    again = client.post(path + "/ready", json=body).json()
    assert again["current_question"]["prepare_until"] == first["current_question"]["prepare_until"]
    clock[0] += 40
    assert client.post(path + "/begin-answer", json=body).json()["current_question"]["phase"] == "answering"


def test_ielts_mock_part3_is_adaptive_without_adding_extra_tasks(ctx):
    session = start(ctx, mode="mock", section="part3")
    total = session["total_questions"]
    for _ in range(total):
        audio = capture(ctx, session).json()
        session = submit(ctx, session, audio_id=audio["id"]).json()
    assert len(session["turns"]) == 4
    assert sum(x["task"] == "adaptive" for x in ctx[1].calls) == 3
    assert all(t["kind"] == "main" for t in session["turns"])


def test_coaching_followups_are_bounded_and_reference_real_answers(ctx):
    session = start(ctx)
    for _ in range(4):
        session = submit(ctx, session).json()
    assert [x["kind"] for x in session["turns"]] == ["main", "followup", "main", "followup"]
    calls = [x for x in ctx[1].calls if x["task"] == "coach_followup"]
    assert len(calls) == 2 and calls[0]["turns"][0]["answer"].startswith("I learned")


def test_duplicate_answer_is_rejected_without_another_model_request(ctx):
    session = start(ctx)
    assert submit(ctx, session).status_code == 200
    count = len(ctx[1].calls)
    assert submit(ctx, session).status_code == 409
    assert len(ctx[1].calls) == count


def test_mock_rejects_text_only_and_audio_from_another_question(ctx):
    session = start(ctx, mode="mock", section="part1")
    assert submit(ctx, session).status_code == 422
    audio = capture(ctx, session).json()
    session = submit(ctx, session, audio_id=audio["id"]).json()
    assert submit(ctx, session, audio_id=audio["id"]).status_code == 422


def test_capture_failure_preserves_recording_and_does_not_invent_text_or_pronunciation(ctx):
    ctx[2].fail = True
    session = start(ctx, mode="mock", section="part1")
    audio = capture(ctx, session)
    assert audio.status_code == 200
    recording = audio.json()
    assert recording["text"] == "" and recording["transcription_error"]
    assert ctx[0].get(f"/api/speaking/sessions/{session['id']}/recordings/{recording['id']}").content == wav()
    session = submit(ctx, session, audio_id=recording["id"]).json()
    assert not session["turns"][0]["transcript_available"]
    report = ctx[0].post(f"/api/speaking/sessions/{session['id']}/finish").json()["report"]
    assert report["source"] == "insufficient_evidence" and not report["dimensions"]


def test_feedback_failure_is_retryable_and_quotes_are_grounded(ctx):
    session = submit(ctx, start(ctx)).json()
    ctx[1].fail_report = True
    path = f"/api/speaking/sessions/{session['id']}/finish"
    session = ctx[0].post(path).json()
    assert session["status"] == "feedback_pending" and session["turns"]
    ctx[1].fail_report = False
    session = ctx[0].post(path).json()
    assert session["status"] == "completed"
    assert len(session["report"]["examples"]) == 1
    assert "improved" not in session["report"]["examples"][0]
    assert session["report"]["overall_score"] is None
    exported = ctx[0].get(path.replace("/finish", "/export"))
    assert exported.status_code == 200 and "server-only-test-key" not in exported.text


def test_official_excerpt_not_offered_as_full_mock_and_mismatches_fail(ctx):
    client = ctx[0]
    base = {"exam": "toefl", "set_id": "ets-full-1-excerpt", "mode": "mock"}
    assert client.post("/api/speaking/sessions", json=base).status_code == 422
    assert client.post("/api/speaking/sessions", json={**base, "mode": "coach"}).status_code == 200
    assert client.post("/api/speaking/sessions", json={"exam": "toefl", "set_id": "ielts-learning"}).status_code == 422
    assert client.post("/api/speaking/sessions", json={"exam": "toefl", "set_id": "toefl-media", "section": "part2"}).status_code == 422


def test_demo_feedback_never_fakes_scores_or_calls_text_provider(ctx):
    session = start(ctx, execution="demo", pace="demo", set_id="ielts-official-excerpts", section="part2")
    session = submit(ctx, session).json()
    assert session["status"] == "completed"
    assert session["report"]["source"] == "offline_demo" and session["report"]["dimensions"] == []
    assert ctx[1].calls == []


def test_recording_length_is_enforced_for_short_repetition_tasks(ctx):
    session = start(ctx, exam="toefl", set_id="toefl-garden", mode="mock", section="repeat")
    assert capture(ctx, session, seconds=10).status_code == 422


def test_endpoints_do_not_leak_secrets_and_validate_origin_and_inputs(ctx):
    client = ctx[0]
    assert "server-only-test-key" not in client.get("/api/speaking/status").text
    assert client.post("/api/speaking/sessions", json={}, headers={"Origin": "https://unrelated.example"}).status_code == 403
    assert client.post("/api/speaking/sessions", json={"unrecognized": True}).status_code == 422
    assert client.get("/api/speaking/resources/unknown").status_code == 404
    assert client.get("/api/speaking/sessions/unknown").status_code == 404
    session = start(ctx)
    assert client.post(f"/api/speaking/sessions/{session['id']}/finish").status_code == 422


def test_nonfinite_scores_are_not_silently_graded():
    raw = {"dimensions": [{"key": key, "score": float('nan')} for key in DIMENSIONS]}
    with pytest.raises(ProviderError):
        normalize_feedback(raw, [], "live")


def test_repeat_only_has_word_comparison_without_invented_language_range_scores(ctx):
    session = start(ctx, exam="toefl", set_id="ets-full-1-excerpt", section="repeat")
    session = submit(ctx, session).json()
    assert session["report"]["source"] == "repetition_comparison"
    assert session["report"]["dimensions"] == []
    assert ctx[1].calls == []


def test_full_autobiographical_expansions_are_filtered_from_suggestions():
    turn = {"id": "t1", "answer": "I learned to bake bread."}
    raw = {"dimensions": [{"key": key, "score": 6} for key in DIMENSIONS], "examples": [
        {"turn_id": "t1", "quote": turn["answer"], "suggestion": "I learned to bake sourdough bread from my aunt, who has been baking for thirty years."},
        {"turn_id": "t1", "quote": turn["answer"], "suggestion": "You could say: I learned to bake sourdough bread from my aunt who has been baking for thirty years."},
        {"turn_id": "t1", "quote": turn["answer"], "suggestion": "Explain what this skill means to you without adding experiences that did not happen."},
    ]}
    report = normalize_feedback(raw, [turn], "live")
    assert len(report["examples"]) == 1
    assert "thirty" not in str(report)


def test_english_catalog_session_feedback_and_errors(ctx):
    client = ctx[0]
    responses = [client.get('/api/speaking/library'), client.get('/api/speaking/status'),
                 client.get('/api/speaking/sessions/missing'),
                 client.post('/api/speaking/sessions', json={}, headers={'Origin': 'https://unrelated.example'})]
    session = start(ctx)
    assert not re.search(r'[\u3400-\u9fff]', json.dumps(session, ensure_ascii=False))
    session = submit(ctx, session).json()
    result = client.post(f"/api/speaking/sessions/{session['id']}/finish")
    assert result.status_code == 200
    assert result.json()['report']['examples'], 'English coaching suggestions must remain visible'
    assert result.json()['turns'][0]['answer'] == 'I learned to repair a bicycle with my brother.'
    responses += [result, client.get('/api/speaking/sessions'),
                  client.get(f"/api/speaking/sessions/{session['id']}/export")]
    for response in responses:
        assert not re.search(r'[\u3400-\u9fff]', response.text), str(response.request.url)
