"""The single wrapper every model call goes through: it times the call and records one
`llm_calls` row (purpose, model, tokens, cost, latency). Prompts and replies are never stored.

Recording never raises and never blocks a hint: a database problem is logged and skipped.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("aporia.llm")


@dataclass(frozen=True)
class CallRecord:
    purpose: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    latency_ms: int
    hint_id: str | None = None


Writer = Callable[[CallRecord], Awaitable[None]]
Hook = Callable[[CallRecord], None]

# The hint a call belongs to (set by the hint endpoint) and an optional per-block accumulator
# (the guard comparison sums judge cost this way).
current_hint_id: ContextVar[str | None] = ContextVar("current_hint_id", default=None)
accumulator: ContextVar[list[CallRecord] | None] = ContextVar("accumulator", default=None)

_writer: Writer | None = None
_hooks: list[Hook] = []


async def _db_writer(rec: CallRecord) -> None:
    import uuid
    from datetime import UTC, datetime

    from app.db import SessionLocal
    from app.models import LLMCall

    async with SessionLocal() as session:
        session.add(
            LLMCall(
                ts=datetime.now(UTC),
                purpose=rec.purpose,
                model=rec.model,
                input_tokens=rec.input_tokens,
                output_tokens=rec.output_tokens,
                cost_usd=rec.cost_usd,
                latency_ms=rec.latency_ms,
                hint_id=uuid.UUID(rec.hint_id) if rec.hint_id else None,
            )
        )
        await session.commit()


def set_writer(writer: Writer | None) -> None:
    """Replaces the sink for call records (tests, the eval scripts). None restores the database."""
    global _writer
    _writer = writer


def add_hook(hook: Hook) -> None:
    """Synchronous observers (metrics) run for every record."""
    if hook not in _hooks:
        _hooks.append(hook)


async def record(rec: CallRecord) -> None:
    bucket = accumulator.get()
    if bucket is not None:
        bucket.append(rec)
    for hook in _hooks:
        try:
            hook(rec)
        except Exception:  # noqa: BLE001
            logger.warning("llm call hook failed")
    try:
        await (_writer or _db_writer)(rec)
    except Exception as exc:  # noqa: BLE001 - bookkeeping must never fail a request
        logger.warning("could not record llm call: %s", type(exc).__name__)


def usage_of(response: Any) -> tuple[int, int]:
    """(prompt tokens, completion tokens) from a LiteLLM response; (0, 0) when not reported."""
    usage = (
        response.get("usage") if isinstance(response, dict) else getattr(response, "usage", None)
    )
    if usage is None:
        return 0, 0

    def field(name: str) -> int:
        value = usage.get(name) if isinstance(usage, dict) else getattr(usage, name, None)
        return int(value or 0)

    return field("prompt_tokens"), field("completion_tokens")


def cost_of(response: Any) -> float:
    """Cost in USD from LiteLLM's price table; 0 for unknown or free (local) models."""
    try:
        import litellm

        return float(litellm.completion_cost(completion_response=response) or 0.0)
    except Exception:  # noqa: BLE001 - unknown model prices are normal (local models)
        return 0.0


async def tracked(
    purpose: str,
    model: str,
    call: Callable[[], Awaitable[Any]],
    response_of: Callable[[Any], Any] = lambda result: result,
) -> Any:
    """Runs `call()`, records one row for it and returns its result. `response_of` picks the
    LiteLLM response out of the result (for example from an Instructor `(parsed, response)`
    pair). A failed call is not recorded (no tokens were produced); the exception propagates."""
    start = time.perf_counter()
    result = await call()
    latency_ms = int((time.perf_counter() - start) * 1000)
    response = response_of(result)
    tokens_in, tokens_out = usage_of(response)
    await record(
        CallRecord(
            purpose=purpose,
            model=model,
            input_tokens=tokens_in,
            output_tokens=tokens_out,
            cost_usd=cost_of(response),
            latency_ms=latency_ms,
            hint_id=current_hint_id.get(),
        )
    )
    return result
