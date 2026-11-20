import logging
import time
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.db import get_session_factory
from app.hints.service import SessionFactory, device_hash
from app.models import Event
from app.ratelimit import enforce_events_rate_limit
from app.schemas.events import EventBatch, EventsAccepted

router = APIRouter(prefix="/v1")
logger = logging.getLogger("aporia.events")

MAX_BODY_BYTES = 32_000
MAX_SKEW_MS = 7 * 24 * 60 * 60 * 1000  # timestamps further than a week from now are rejected


@router.post("/events", status_code=202, response_model=EventsAccepted)
async def post_events(
    request: Request,
    batch: EventBatch,
    device_id: str = Depends(enforce_events_rate_limit),
    factory: SessionFactory = Depends(get_session_factory),
) -> EventsAccepted:
    """Stores a batch of allowlisted telemetry events (the extension only sends after opt-in)."""
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="request body too large")
    now_ms = int(time.time() * 1000)
    if any(abs(e.ts - now_ms) > MAX_SKEW_MS for e in batch.events):
        raise HTTPException(status_code=422, detail="event timestamp out of range")

    device = device_hash(device_id)
    rows = []
    for e in batch.events:
        props: dict[str, Any] = {
            k: v
            for k, v in (
                ("level", e.level),
                ("reason", e.reason),
                ("rating", e.rating),
                ("was_stuck", e.was_stuck),
            )
            if v is not None
        }
        rows.append(
            Event(
                device_hash=device,
                type=e.type,
                slug=e.slug,
                props=props,
                ts=datetime.fromtimestamp(e.ts / 1000, tz=UTC),
            )
        )
    try:
        async with factory() as session:
            session.add_all(rows)
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - telemetry must never surface errors to the student
        logger.warning("could not store events: %s", type(exc).__name__)
    return EventsAccepted(accepted=len(rows))
