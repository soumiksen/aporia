"""A daily spend limit. When today's `llm_calls.cost_usd` reaches APORIA_DAILY_BUDGET_USD the
hint endpoint stops calling models and serves safe hints (logged at WARNING)."""

import logging
import time
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import LLMCall

logger = logging.getLogger("aporia.llm")

CACHE_SECONDS = 30  # the sum is re-read at most this often
WARN_EVERY_SECONDS = 60

_cache: tuple[float, float] | None = None  # (read at, spent)
_last_warning = 0.0


def day_start(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


async def spent_today(
    factory: async_sessionmaker[AsyncSession], now: datetime | None = None
) -> float:
    async with factory() as session:
        total = await session.scalar(
            select(func.coalesce(func.sum(LLMCall.cost_usd), 0.0)).where(
                LLMCall.ts >= day_start(now)
            )
        )
    return float(total or 0.0)


async def budget_exceeded(
    factory: async_sessionmaker[AsyncSession],
    budget_usd: float,
    *,
    now: datetime | None = None,
    clock: float | None = None,
) -> bool:
    """True when the day's spend has reached the budget. Off when budget_usd <= 0. A database
    problem never blocks hints (it reports 'not exceeded')."""
    global _cache, _last_warning
    if budget_usd <= 0:
        return False
    t = time.monotonic() if clock is None else clock
    try:
        if _cache is None or t - _cache[0] > CACHE_SECONDS:
            _cache = (t, await spent_today(factory, now))
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not read today's llm spend: %s", type(exc).__name__)
        return False
    exceeded = _cache[1] >= budget_usd
    if exceeded and t - _last_warning > WARN_EVERY_SECONDS:
        _last_warning = t
        logger.warning(
            "daily LLM budget reached ($%.4f of $%.2f): serving safe hints", _cache[1], budget_usd
        )
    return exceeded


def reset_budget_cache() -> None:
    global _cache, _last_warning
    _cache, _last_warning = None, 0.0
