import logging
from collections.abc import Awaitable, Callable
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.config import get_settings

logger = logging.getLogger("aporia.queue")

Enqueue = Callable[[str, dict[str, Any]], Awaitable[bool]]

_pool: ArqRedis | None = None


async def enqueue_reference(slug: str, problem: dict[str, Any]) -> bool:
    """Enqueues build_reference_job once per slug (job id dedupes). Never raises."""
    global _pool
    try:
        if _pool is None:
            _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
        job = await _pool.enqueue_job(
            "build_reference_job", slug, problem, _job_id=f"reference:{slug}"
        )
        return job is not None
    except Exception as exc:  # noqa: BLE001 - enqueue failure must never break a hint request
        logger.warning("could not enqueue reference build: %s", type(exc).__name__)
        return False


def get_enqueue() -> Enqueue:
    return enqueue_reference
