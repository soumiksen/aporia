"""Hint ladder: pure functions and dataclasses, no I/O."""

from dataclasses import dataclass

MAX_LEVEL = 4
ESCALATE_AFTER_FAILED_ATTEMPTS = 3


@dataclass(frozen=True)
class LadderState:
    level_reached: int = 0  # highest level served so far for this (device, problem); 0 = none
    attempts_since_hint: int = 0
    last_verdict: str | None = None


def next_level(state: LadderState, requested_level: int | None, failed_attempts: int) -> int:
    """Chooses the level to serve (always within 1..MAX_LEVEL).

    - An explicit request is honoured but may not skip a rung: it is capped at
      level_reached + 1. Asking for a lower level re-serves that lower level.
    - With no request, the current rung is re-served (at least level 1).
    - After ESCALATE_AFTER_FAILED_ATTEMPTS failed attempts since the last hint, escalate by one
      level above level_reached, whatever was requested (never lower than the request).
    """
    reached = max(0, min(state.level_reached, MAX_LEVEL))
    ceiling = min(MAX_LEVEL, reached + 1)
    if requested_level is None:
        base = max(1, reached)
    else:
        base = max(1, min(requested_level, ceiling))
    failed = max(failed_attempts, state.attempts_since_hint)
    auto = ceiling if failed >= ESCALATE_AFTER_FAILED_ATTEMPTS else 0
    return min(MAX_LEVEL, max(base, auto))


def after_hint(state: LadderState, served_level: int) -> LadderState:
    """State after serving a hint: the rung is recorded and the attempt counter resets."""
    return LadderState(
        level_reached=max(state.level_reached, min(served_level, MAX_LEVEL)),
        attempts_since_hint=0,
        last_verdict=state.last_verdict,
    )


def with_attempts(
    state: LadderState, failed_attempts: int, last_verdict: str | None
) -> LadderState:
    """State updated with the client's count of failed attempts since its last hint."""
    return LadderState(
        level_reached=state.level_reached,
        attempts_since_hint=max(0, failed_attempts),
        last_verdict=last_verdict if last_verdict is not None else state.last_verdict,
    )
