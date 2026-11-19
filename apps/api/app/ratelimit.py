import logging
import time
from typing import Protocol, cast

from fastapi import Depends, Header, HTTPException
from redis.asyncio import Redis

from app.config import Settings, get_settings

logger = logging.getLogger("aporia.ratelimit")

WINDOW_SECONDS = 60


class RedisLike(Protocol):
    async def incr(self, name: str) -> int: ...
    async def expire(self, name: str, time: int) -> bool: ...


def window_key(device_id: str, now: float, window: int = WINDOW_SECONDS) -> str:
    """Fixed-window key: one counter per device per window."""
    return f"rl:hint:{device_id}:{int(now // window)}"


def is_allowed(count: int, limit: int) -> bool:
    return count <= limit


async def hit(redis: RedisLike, device_id: str, limit: int, now: float | None = None) -> bool:
    """Records a request and returns whether it is within the limit."""
    key = window_key(device_id, time.time() if now is None else now)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, WINDOW_SECONDS * 2)
    return is_allowed(count, limit)


_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        _client = Redis.from_url(get_settings().redis_url)
    return _client


async def require_device(x_aporia_device: str | None = Header(default=None)) -> str:
    if not x_aporia_device or len(x_aporia_device) > 128:
        raise HTTPException(status_code=400, detail="Missing or invalid X-Aporia-Device header")
    return x_aporia_device


async def enforce_rate_limit(
    device_id: str = Depends(require_device),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> str:
    try:
        allowed = await hit(cast(RedisLike, redis), device_id, settings.rate_limit_per_minute)
    except Exception:
        # Fail open: a limiter outage must not block hints. /readyz reports Redis health.
        logger.warning("rate limiter unavailable; allowing request")
        return device_id
    if not allowed:
        raise HTTPException(
            status_code=429, detail="Rate limit exceeded", headers={"Retry-After": "60"}
        )
    return device_id
