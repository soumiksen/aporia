"""Optional forwarding of stored usage events to PostHog. Skipped entirely without a key."""

import logging
from typing import Any

import httpx
from sqlalchemy import select

from app.config import Settings
from app.hints.service import SessionFactory
from app.models import Event

logger = logging.getLogger("aporia.posthog")

CURSOR_KEY = "posthog:last_event_id"
BATCH_SIZE = 100
MAX_BATCHES_PER_RUN = 10


def to_posthog(event: Event) -> dict[str, Any]:
    """The stored fields only: nothing here can contain code or problem text."""
    props: dict[str, Any] = {"$lib": "aporia-api", **(event.props or {})}
    if event.slug:
        props["slug"] = event.slug
    return {
        "event": event.type,
        "distinct_id": event.device_hash,  # already a SHA-256 of the random device id
        "timestamp": event.ts.isoformat(),
        "properties": props,
    }


async def forward_events(
    factory: SessionFactory,
    redis: Any,
    settings: Settings,
    client: httpx.AsyncClient,
) -> int:
    """Sends events newer than the stored cursor, oldest first. Returns how many were forwarded.

    The cursor only advances after PostHog accepted a batch, so a failure is retried next run.
    """
    if not settings.posthog_api_key:
        return 0
    forwarded = 0
    for _ in range(MAX_BATCHES_PER_RUN):
        raw = await redis.get(CURSOR_KEY)
        cursor = int(raw) if raw else 0
        async with factory() as session:
            rows = (
                await session.scalars(
                    select(Event).where(Event.id > cursor).order_by(Event.id).limit(BATCH_SIZE)
                )
            ).all()
        if not rows:
            break
        try:
            res = await client.post(
                f"{settings.posthog_host.rstrip('/')}/batch/",
                json={"api_key": settings.posthog_api_key, "batch": [to_posthog(e) for e in rows]},
            )
            res.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("posthog forwarding failed: %s", type(exc).__name__)
            break
        await redis.set(CURSOR_KEY, rows[-1].id)
        forwarded += len(rows)
        if len(rows) < BATCH_SIZE:
            break
    return forwarded
