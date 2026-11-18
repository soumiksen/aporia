from typing import Any

from pydantic import BaseModel, Field


class ProblemContext(BaseModel):
    slug: str
    title: str
    difficulty: str
    tags: list[str]
    content_text: str
    meta: dict[str, Any] | None = None


class HintRequest(BaseModel):
    problem: ProblemContext
    # Size limits (code <= 50_000 chars etc.) are enforced in the endpoint so they return 413.
    code: str
    language: str
    level: int = Field(default=1, ge=1, le=4)  # only level 1 is implemented in Stage 1
    student_message: str | None = None


class TokenEvent(BaseModel):
    text: str


class DoneEvent(BaseModel):
    hint_id: str
    level: int
    sources: list[str] = Field(default_factory=list)


class ErrorEvent(BaseModel):
    code: str
    message: str
