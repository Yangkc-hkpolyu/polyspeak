from collections import Counter
import asyncio
from datetime import date
import re
from urllib.parse import urlsplit

import pytest

from backend.speaking.bank import catalog, get_set
from backend.speaking.collected_bank import DATA, SOURCE_BY_ID
from backend.speaking.engine import SpeakingEngine
from backend.speaking.schemas import AnswerRequest, ExamSetup
from backend.speaking.store import InterviewStore


def test_collected_sources_and_question_identity():
    questions = DATA["questions"]
    assert len({q["id"] for q in questions}) == len(questions)
    assert len({re.sub(r"[^a-z0-9]", "", q["text"].lower()) for q in questions}) == len(questions)
    assert len(SOURCE_BY_ID) == len(DATA["sources"])
    assert len(questions) > 250
    assert {q["stage"] for q in questions} == {"part1", "part2", "part3", "interview"}
    for q in questions:
        source = SOURCE_BY_ID[q["source_id"]]
        assert q["exam"] == source["exam"]
        assert q["season"] == source["season"]
        assert source["published_on"] <= DATA["verified_on"]
        assert len(source["page_sha256"]) == 64
        assert urlsplit(source["url"]).hostname in {"ielts.koolearn.com", "toefl.xdf.cn", "www.testdaily.cn"}
        if q["exam"] == "toefl":
            assert source["format_version"] == "toefl_2026"
            assert date.fromisoformat(source["reported_exam_on"]) >= date(2026, 1, 21)
        if q["wording"] == "translated_recall":
            assert source["kind"] == "candidate_recall"
        if q["wording"] == "edited_excerpt":
            assert q["editorial_edits"]
    assert all(s["excerpt_words"] <= 25 and s.get("derived_words", 0) <= 200 for s in DATA["sources"])


def test_each_question_is_practicable_without_becoming_a_full_mock():
    library = catalog()
    assert library["collection_stats"]["by_exam"] == dict(Counter(q["exam"] for q in DATA["questions"]))
    assert len(library["sources"]) == 7
    assert any(n["publisher"] == "雅思哥" and n["kind"] == "unimported" for n in library["access_notes"])
    for q in library["collected_questions"]:
        single = get_set(q["set_id"])
        assert single["mock_allowed"] is False
        assert len(single["questions"]) == 1
        item = single["questions"][0]
        assert item["text"] == q["text"] and item["stage"] == q["stage"]
        assert item["wording"] == q["wording"]
        assert item["provenance"]["url"] == SOURCE_BY_ID[q["source_id"]]["url"]


def test_recalled_question_keeps_attribution_but_generated_followup_does_not(tmp_path):
    class Provider:
        async def complete(self, _system, data):
            assert data["task"] == "coach_followup"
            return {"question": "Could you give a specific example?"}

    entry = next(q for q in DATA["questions"] if q["wording"] == "translated_recall")
    store = InterviewStore(tmp_path / "questions.sqlite3")
    engine = SpeakingEngine(store, Provider(), clock=lambda: 1000)
    setup = ExamSetup(exam="toefl", set_id="bank-" + entry["id"], mode="coach")
    with pytest.raises(ValueError):
        engine.start(setup.model_copy(update={"mode": "mock"}))
    session = engine.start(setup)
    result = asyncio.run(engine.answer(session["id"], AnswerRequest(question_id=session["pending_question_id"], answer="I read with my friends and discuss a book every week.")))
    assert result["turns"][0]["wording"] == "translated_recall"
    assert result["turns"][0]["provenance"]["url"].startswith("https://www.testdaily.cn/")
    followup = result["current_question"]
    assert followup["source_kind"] == "ai_generated"
    assert not followup.get("provenance") and not followup.get("wording")
