from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EventType = Literal[
    "stuck_prompt_shown",
    "stuck_prompt_accepted",
    "stuck_prompt_dismissed",
    "hint_requested",
    "hint_rated",
    "stuck_label",
]
StuckReason = Literal["consecutive_failures", "repeated_failure", "inactivity", "low_progress"]

MAX_BATCH = 50


class EventIn(BaseModel):
    """One telemetry event. Strict: unknown fields are rejected, so code or problem text can never
    arrive through a stray field."""

    model_config = ConfigDict(extra="forbid")

    type: EventType
    ts: int = Field(description="epoch milliseconds")
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9-]{0,99}$")
    level: int | None = Field(default=None, ge=1, le=4)
    reason: StuckReason | None = None
    rating: int | None = Field(default=None, ge=1, le=5)
    was_stuck: bool | None = None


class EventBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[EventIn] = Field(min_length=1, max_length=MAX_BATCH)


class EventsAccepted(BaseModel):
    accepted: int
