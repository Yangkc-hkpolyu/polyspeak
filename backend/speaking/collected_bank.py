"""Reviewed institutional excerpts, with provenance kept through a practice turn."""
from collections import Counter
from copy import deepcopy
import json
from pathlib import Path

DATA = json.loads((Path(__file__).parent / "data/collected_questions.json").read_text(encoding="utf-8"))
SOURCE_BY_ID = {s["id"]: s for s in DATA["sources"]}


def collection_sets(question_factory):
    sets = []
    for entry in DATA["questions"]:
        source = SOURCE_BY_ID[entry["source_id"]]
        item = question_factory(entry["stage"], entry["text"], source_id=entry["source_id"])
        item.update({key: deepcopy(entry[key]) for key in ("source_kind", "wording", "topic", "season")})
        item["bank_question_id"] = entry["id"]
        item["provenance"] = {key: source[key] for key in ("publisher", "title", "url", "published_on", "reported_exam_on", "verified_on") if source.get(key)}
        item["context"] = "话题：" + entry["topic"] + "。题干节选，完整题卡及问题见来源。"
        if entry.get("editorial_edits"):
            item["editorial_edits"] = deepcopy(entry["editorial_edits"])
        sets.append({"id": "bank-" + entry["id"], "exam": entry["exam"], "title": entry["topic"], "kind": entry["source_kind"], "from_collection": True, "mock_allowed": False, "questions": [item]})
    return sets


def collection_catalog():
    items = deepcopy(DATA["questions"])
    for item in items:
        item["set_id"] = "bank-" + item["id"]
    return {"collected_questions": items, "web_sources": deepcopy(DATA["sources"]), "access_notes": deepcopy(DATA["access_notes"]), "collection_stats": {"questions": len(items), "sources": len(DATA["sources"]), "by_exam": dict(Counter(q["exam"] for q in items)), "by_season": dict(Counter(q["season"] for q in items)), "by_wording": dict(Counter(q["wording"] for q in items))}}
