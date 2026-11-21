import logging
from collections.abc import Awaitable, Callable
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings

logger = logging.getLogger("aporia.queue")

Enqueue = Callable[[str, dict[str, Any]], Awaitable[bool]]

_pool: ArqRedis | None = None


async def _enqueue(function: str, prefix: str, slug: str, problem: dict[str, Any]) -> bool:
    """Enqueues a job once per slug (the job id dedupes). Never raises."""
    global _pool
    try:
        if _pool is None:
            _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        job = await _pool.enqueue_job(function, slug, problem, _job_id=f"{prefix}:{slug}")
        return job is not None
    except Exception as exc:  # noqa: BLE001 - enqueue failure must never break a hint request
        logger.warning("could not enqueue %s: %s", function, type(exc).__name__)
        return False


async def enqueue_reference(slug: str, problem: dict[str, Any]) -> bool:
    return await _enqueue("build_reference_job", "reference", slug, problem)


async def enqueue_summary(slug: str, problem: dict[str, Any]) -> bool:
    return await _enqueue("summarize_problem_job", "summary", slug, problem)


def get_enqueue() -> Enqueue:
    return enqueue_reference


def get_enqueue_summary() -> Enqueue:
    return enqueue_summary
