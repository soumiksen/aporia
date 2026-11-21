import logging

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict, Field

from app.db import get_session_factory
from app.hints.service import SessionFactory, device_hash
from app.learner.service import record_attempt
from app.ratelimit import enforce_events_rate_limit

router = APIRouter(prefix="/v1")
logger = logging.getLogger("aporia.attempts")


class AttemptRequest(BaseModel):
    """A submission outcome. No code, ever (extra fields are rejected)."""

    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=200, pattern=r"^[a-z0-9][a-z0-9-]*$")
    verdict: str = Field(min_length=1, max_length=40)


@router.post("/attempts", status_code=204)
async def post_attempt(
    body: AttemptRequest,
    device_id: str = Depends(enforce_events_rate_limit),
    factory: SessionFactory = Depends(get_session_factory),
) -> Response:
    """Updates the learner model for the problem's concepts. Storage errors never fail the call."""
    try:
        async with factory() as session:
            await record_attempt(session, device_hash(device_id), body.slug, body.verdict)
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not record attempt: %s", type(exc).__name__)
    return Response(status_code=204)
