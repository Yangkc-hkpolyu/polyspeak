import asyncio
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import re
import time
import uuid

from .bank import get_set
from .errors import public_error_message
from .feedback import concise_explanation, normalize_feedback, repetition_check
from .provider import ProviderError
from .schemas import ExamSetup
from .store import ConflictError
from .layered_feedback import LayeredEvaluator, grounded_polishing

PROMPTS = Path(__file__).parent / "prompts"


class SpeakingEngine:
    def __init__(self, store, provider, clock=time.time):
        self.store, self.provider, self.clock = store, provider, clock
        self.locks = {}
        self.examiner_prompt = (PROMPTS / "examiner.txt").read_text(encoding="utf-8")
        self.feedback_prompt = (PROMPTS / "feedback.txt").read_text(encoding="utf-8")
        self.evaluator = LayeredEvaluator(provider)
        self.evaluation_tasks = {}

    def evaluate_turn(self, turn):
        task = self.evaluation_tasks.get(turn["id"])
        if task is None or task.cancelled() or (task.done() and task.exception() is not None):
            task = asyncio.create_task(self.evaluator.evaluate(deepcopy(turn)))
            task.add_done_callback(lambda finished: finished.exception() if not finished.cancelled() else None)
            self.evaluation_tasks[turn["id"]] = task
        return task

    async def layered_report(self, session):
        turns = [turn for turn in session["turns"] if not turn["skipped"] and turn["transcript_available"] and turn["stage"] != "repeat"]
        pending = [turn for turn in turns if not turn.get("evaluation")]
        results = await asyncio.gather(*(self.evaluate_turn(turn) for turn in pending), return_exceptions=True)
        failed = False
        for turn, result in zip(pending, results):
            if isinstance(result, BaseException):
                public_error_message(result, "A per-question evaluation could not be completed.", getattr(self.provider, "settings", None))
                failed = True
            else:
                turn["evaluation"] = result
        if failed:
            raise ProviderError("Some per-question evaluations could not be completed. Your answers and recordings are saved. Please retry feedback.")
        return self.evaluator.aggregate(turns)

    async def close(self):
        for task in self.evaluation_tasks.values():
            task.cancel()
        await asyncio.gather(*self.evaluation_tasks.values(), return_exceptions=True)

    def lock(self, session_id):
        return self.locks.setdefault(session_id, asyncio.Lock())

    def start(self, setup: ExamSetup):
        bank = get_set(setup.set_id)
        if bank["exam"] != setup.exam:
            raise ValueError("The question set does not match the selected exam.")
        if not bank["mock_allowed"] and setup.mode == "mock":
            raise ValueError("Question excerpts are for section practice. Choose an original practice set for a full mock exam.")
        allowed = {"ielts": {"full", "part1", "part2", "part3"}, "toefl": {"full", "repeat", "interview"}}
        if setup.section not in allowed[setup.exam]:
            raise ValueError("The selected section is not available for this exam.")
        plan = [q for q in bank["questions"] if setup.section == "full" or q["stage"] == setup.section or setup.section == "part2" and q["stage"] == "rounding"]
        if not plan:
            raise ValueError("This question set does not include the selected section.")
        if setup.pace == "demo":
            for q in plan:
                q["prepare_seconds"] = 3 if q["prepare_seconds"] else 0
                q["answer_seconds"] = min(q["answer_seconds"], 12)
        session = {"id": uuid.uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(), "setup": setup.model_dump(), "set_title": bank["title"], "plan": plan, "index": 0, "followup_count": 0, "status": "active", "messages": [], "turns": [], "report": None, "report_error": None, "notices": [], "recordings": {}}
        self.add_question(session, plan[0])
        self.store.create(session)
        return self.public(session)

    def add_question(self, session, item, followup=False):
        question = {**deepcopy(item), "id": uuid.uuid4().hex, "role": "assistant", "number": session["index"] + 1, "kind": "followup" if followup else "main", "phase": "listening", "prepare_until": None, "answer_until": None}
        session["messages"].append(question)
        session["pending_question_id"] = question["id"]
        return question

    @staticmethod
    def pending(session, question_id):
        if session["status"] != "active" or session["pending_question_id"] != question_id:
            raise ConflictError("This question has already been processed or the session has ended. Refresh to continue.")
        return next(x for x in session["messages"] if x["id"] == question_id)

    async def ready(self, session_id, question_id, begin=False):
        async with self.lock(session_id):
            session = self.store.get(session_id)
            q = self.pending(session, question_id)
            now = self.clock()
            if q["phase"] == "listening":
                q["prepare_until"] = now + q["prepare_seconds"]
                q["answer_until"] = q["prepare_until"] + q["answer_seconds"]
                q["phase"] = "preparing" if q["prepare_seconds"] else "answering"
            if begin and q["phase"] == "preparing":
                if session["setup"]["mode"] == "mock" and now < q["prepare_until"]:
                    raise ValueError("The preparation time has not ended yet.")
                if session["setup"]["mode"] == "coach":
                    q["prepare_until"] = now
                    q["answer_until"] = now + q["answer_seconds"]
                q["phase"] = "answering"
            self.store.save(session)
            return self.public(session)

    async def store_recording(self, session_id, question_id, recording):
        async with self.lock(session_id):
            session = self.store.get(session_id)
            self.pending(session, question_id)
            session["recordings"][recording["id"]] = recording
            self.store.save(session)

    async def generated_question(self, session, task, question):
        if session["setup"]["execution"] == "demo":
            return "What makes that important, and can you give a specific example?" if task == "coach_followup" else question["text"]
        try:
            raw = await self.provider.complete(self.examiner_prompt, {"task": task, "exam": session["setup"]["exam"], "mode": session["setup"]["mode"], "planned_question": question, "long_turn_topic": next((q["text"] for q in session["plan"] if q["stage"] == "part2"), ""), "turns": session["turns"][-5:]})
            value = raw.get("question")
            if not isinstance(value, str) or not 5 <= len(value.strip()) <= 600 or re.search(r"[\u3400-\u9fff\uf900-\ufaff]", value):
                raise ProviderError("Invalid follow-up")
            return value.strip()
        except ProviderError:
            session["notices"].append("A follow-up question could not be generated. The session is continuing with the planned question.")
            return None

    async def answer(self, session_id, request):
        async with self.lock(session_id):
            session = self.store.get(session_id)
            q = self.pending(session, request.question_id)
            recording = session["recordings"].get(request.audio_id) if request.audio_id else None
            if request.audio_id and (not recording or recording["question_id"] != q["id"]):
                raise ValueError("This recording does not belong to the current question. Please record it again.")
            if not request.skipped and session["setup"]["mode"] == "mock" and not recording:
                raise ValueError("Mock exams require recorded answers. Use coaching mode for typed answers.")
            answer = (recording.get("text", "") if session["setup"]["mode"] == "mock" and recording else request.answer.strip() or (recording or {}).get("text", ""))
            if not request.skipped and not recording and len(answer) < 2:
                raise ValueError("Record or type an answer first.")
            turn = {"id": uuid.uuid4().hex, "question_id": q["id"], "question": q["text"], "stage": q["stage"], "kind": q["kind"], "answer": answer if not request.skipped else "", "skipped": request.skipped, "source_kind": q["source_kind"], "source_id": q.get("source_id"), "audio_id": request.audio_id if not request.skipped else None, "duration_seconds": (recording or {}).get("duration_seconds"), "transcript_available": bool(answer), "pronunciation": (recording or {}).get("pronunciation", {"status": "no_audio", "message": "No assessable recording was provided for this question."})}
            for key in ("bank_question_id", "wording", "season", "topic", "provenance", "editorial_edits"):
                if key in q:
                    turn[key] = deepcopy(q[key])
            if q["task_type"] == "repeat" and answer and not request.skipped:
                turn["repetition"] = repetition_check(q["text"], answer)
            session["turns"].append(turn)
            turn["card"] = q.get("card", [])
            turn["configured_answer_seconds"] = q["answer_seconds"]
            turn["practice_pace"] = session["setup"]["pace"]
            if recording and recording.get("transcription_error"):
                turn["transcription_error"] = recording["transcription_error"]
            if session["setup"]["execution"] == "live" and not request.skipped and answer and q["task_type"] != "repeat":
                self.evaluate_turn(turn)
            q["phase"] = "answered"
            session["messages"].append({"id": turn["id"], "role": "user", "text": answer or ("[Skipped]" if request.skipped else "[Recording saved; transcript unavailable]"), "audio_id": turn["audio_id"]})
            followup = None
            if session["setup"]["mode"] == "coach" and not request.skipped and answer and session["followup_count"] == 0 and q["task_type"] in ("interview", "discussion") and q["stage"] != "rounding":
                followup = await self.generated_question(session, "coach_followup", q)
            if followup:
                session["followup_count"] = 1
                followup_item = {k: v for k, v in q.items() if k not in ("bank_question_id", "wording", "season", "provenance", "editorial_edits", "context")}
                self.add_question(session, {**followup_item, "text": followup, "card": [], "source_kind": "ai_generated", "source_id": None}, followup=True)
            else:
                session["index"] += 1
                session["followup_count"] = 0
                if session["index"] < len(session["plan"]):
                    next_q = deepcopy(session["plan"][session["index"]])
                    if session["setup"]["mode"] == "mock" and session["setup"]["exam"] == "ielts" and next_q["stage"] == "part3" and not request.skipped:
                        adaptive = await self.generated_question(session, "adaptive", next_q)
                        if adaptive and session["setup"]["execution"] == "live":
                            next_q.update(text=adaptive, source_kind="ai_generated", source_id=None)
                    self.add_question(session, next_q)
                else:
                    session.update(status="feedback_pending", pending_question_id=None)
            # Save audio and answers before an expensive/fallible report request.
            self.store.save(session)
            if session["status"] == "feedback_pending":
                await self.generate_report(session)
            return self.public(session)

    async def generate_report(self, session):
        usable = [t for t in session["turns"] if not t["skipped"] and t["transcript_available"]]
        try:
            if session["setup"]["execution"] == "demo" or not usable:
                raw = {"summary": "This is an offline demonstration. Model scores are not generated." if usable else "No transcript is available to analyze. Replay your recordings in the conversation or start another practice session.", "strengths": [], "improvements": [], "next_steps": ["Choose one question and answer it again with one point, one reason, and one specific example."], "examples": []}
                report = normalize_feedback(raw, session["turns"], "demo")
                if session["setup"]["execution"] == "live":
                    report["source"] = "insufficient_evidence"
            elif all(t["stage"] == "repeat" for t in usable):
                report = normalize_feedback({"summary": "Repetition practice is complete. Replay the recording alongside the target sentence and recognized words below. Text differences do not prove pronunciation errors. Pronunciation feedback is available only when Azure returns an assessment of the actual audio.", "next_steps": ["Replay sentences with word differences, then repeat them in meaningful phrase groups."]}, session["turns"], "demo")
                report["source"] = "repetition_comparison"
            else:
                layered = await self.layered_report(session)
                raw = await self.provider.complete(self.feedback_prompt, {"task": "feedback", "setup": session["setup"], "turns": [t for t in session["turns"] if t["stage"] != "repeat"], "planned_tasks": len(session["plan"]), "features_summary": layered["features_summary"], "aspects_summary": layered["aspects_summary"]})
                report = normalize_feedback(raw, session["turns"], "live")
                report["layered"] = layered
                comments = {item["key"]: item["comment"] for item in report["dimensions"]}
                report["dimensions"] = [{"key": key, "score": item["score"], "comment": comments.get(key, "Based on the per-question evaluations of the answers submitted in this session.")}
                                        for key, item in layered["aspects_summary"].items()]
                report["scope"] = "Feedback covers per-question features, language dimensions, and an overall summary. Scores are practice metrics, not IELTS bands or TOEFL scores. Audio and video criteria remain unassessed when evidence is unavailable."
            report["coverage"] = {"answered": len(usable), "submitted": len(session["turns"]), "skipped": sum(t["skipped"] for t in session["turns"]), "planned": len(session["plan"]), "early_finish": session["index"] < len(session["plan"])}
            session.update(report=report, status="completed", report_error=None)
        except ProviderError as exc:
            session["report_error"] = str(exc)
        self.store.save(session)

    async def finish(self, session_id):
        async with self.lock(session_id):
            session = self.store.get(session_id)
            if session["status"] == "completed":
                return self.public(session)
            if not session["turns"]:
                raise ValueError("Submit at least one answer first.")
            session.update(status="feedback_pending", pending_question_id=None)
            self.store.save(session)
            await self.generate_report(session)
            return self.public(session)

    def public(self, session):
        result = {k: deepcopy(v) for k, v in session.items() if k not in ("plan", "recordings")}
        if result.get("report"):
            # Apply the same display rules to reports created before validation changes.
            result["report"]["examples"] = [{k: v for k, v in item.items() if k != "improved"} for item in result["report"].get("examples", []) if concise_explanation(item.get("suggestion"))]
            for question in result["report"].get("layered", {}).get("questions", []):
                polishing = question.get("polishing", {})
                question["polishing"] = grounded_polishing(polishing.get("original", ""), polishing)
        answered = {t["question_id"] for t in session["turns"]}
        for q in result["messages"]:
            if q.get("task_type") == "repeat" and q["id"] not in answered:
                q["text"] = "Listen carefully, then repeat the sentence once."
            elif q.get("role") == "assistant" and q.get("phase") == "listening" and session["setup"]["mode"] == "mock":
                q["text"] = "Listen as Nora introduces the long-turn topic." if q["stage"] == "part2" else "Listen to Nora's question."
                q["card"] = []
        result["current_question"] = next((x for x in result["messages"] if x["id"] == session.get("pending_question_id")), None)
        result["total_questions"] = len(session["plan"])
        result["completed_questions"] = min(session["index"], len(session["plan"]))
        result["server_time"] = self.clock()
        return result
