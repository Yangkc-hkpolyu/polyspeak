from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExamSetup(StrictInput):
    exam: Literal["ielts", "toefl"] = "ielts"
    set_id: str = Field(default="ielts-learning", max_length=80)
    mode: Literal["mock", "coach"] = "mock"
    section: Literal["full", "part1", "part2", "part3", "repeat", "interview"] = "full"
    execution: Literal["live", "demo"] = "live"
    pace: Literal["standard", "demo"] = "standard"
    candidate_name: str = Field(default="", max_length=60)


class QuestionRequest(StrictInput):
    question_id: str = Field(min_length=1, max_length=64)


class AnswerRequest(QuestionRequest):
    answer: str = Field(default="", max_length=12000)
    audio_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    skipped: bool = False


class SpeechRequest(StrictInput):
    text: str = Field(min_length=1, max_length=600)
    language: Literal["en", "zh"] = "en"
