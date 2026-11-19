import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import redis.asyncio
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.db import get_session_factory
from app.guard.guard import GuardDecision, GuardedResult, check, guard_enabled, guarded_reply
from app.guard.llm_judge import Judge, get_judge
from app.hints.ladder import after_hint, next_level, with_attempts
from app.hints.service import (
    SessionFactory,
    build_messages,
    chunk_text,
    device_hash,
    lookup_problem,
    rate_hint,
    save_hint,
)
from app.hints.state_store import load_state, save_state
from app.llm.gateway import LLMConfigError, complete, ensure_configured
from app.ratelimit import enforce_rate_limit, get_redis, require_device
from app.reference.queue import Enqueue, get_enqueue
from app.schemas.hint import DoneEvent, ErrorEvent, HintRequest, RatingRequest, TokenEvent

router = APIRouter(prefix="/v1")
logger = logging.getLogger("aporia.hint")

MAX_CODE_CHARS = 50_000
MAX_CONTENT_CHARS = 50_000
MAX_MESSAGE_CHARS = 2_000
MAX_BODY_BYTES = 256_000

Generator = Callable[..., Awaitable[str]]


def get_generator() -> Generator:
    return complete


def sse(event: str, payload: str) -> str:
    return f"event: {event}\ndata: {payload}\n\n"


def check_limits(req: HintRequest) -> None:
    if len(req.code) > MAX_CODE_CHARS:
        raise HTTPException(status_code=413, detail=f"code exceeds {MAX_CODE_CHARS} characters")
    if len(req.problem.content_text) > MAX_CONTENT_CHARS:
        raise HTTPException(status_code=413, detail="problem content_text is too long")
    if req.student_message and len(req.student_message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail="student_message is too long")


@router.post("/hint")
async def post_hint(
    request: Request,
    body: HintRequest,
    device_id: str = Depends(enforce_rate_limit),
    factory: SessionFactory = Depends(get_session_factory),
    redis_client: redis.asyncio.Redis = Depends(get_redis),
    enqueue: Enqueue = Depends(get_enqueue),
    generator: Generator = Depends(get_generator),
    judge: Judge = Depends(get_judge),
    settings: Settings = Depends(get_settings),
    x_aporia_disable_guard: str | None = Header(default=None),
) -> StreamingResponse:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="request body too large")
    check_limits(body)
    try:
        ensure_configured("APORIA_MODEL_FAST")
    except LLMConfigError as exc:
        logger.error("%s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    hint_id = str(uuid.uuid4())
    device = device_hash(device_id)
    slug = body.problem.slug
    info = await lookup_problem(factory, enqueue, body)

    state = with_attempts(
        await load_state(redis_client, device, slug), body.failed_attempts, body.last_verdict
    )
    level = next_level(state, body.level, body.failed_attempts)
    guard_on = guard_enabled(settings, x_aporia_disable_guard)
    metadata: dict[str, Any] = {"hint_id": hint_id, "level": level, "device_hash": device}
    logger.info(
        "hint requested slug=%s level=%d hint_id=%s guard=%s", slug, level, hint_id, guard_on
    )

    async def generate(feedback: str | None) -> str:
        return await generator(
            build_messages(body, level, feedback), "APORIA_MODEL_FAST", metadata=metadata
        )

    async def check_draft(draft: str) -> GuardDecision:
        return await check(draft, level, body.problem, info.reference_source, judge)

    async def events() -> AsyncIterator[str]:
        try:
            if guard_on:
                result = await guarded_reply(generate, check_draft, slug=slug, level=level)
            else:  # evaluation only (APORIA_ENV=eval)
                result = GuardedResult(await generate(None), {"guard": "disabled"}, 0, False)
        except Exception as exc:  # noqa: BLE001 - never leak provider details or student code
            logger.error("hint generation failed: %s", type(exc).__name__)
            err = ErrorEvent(
                code="llm_error", message="Could not generate a hint. Please try again."
            )
            yield sse("error", err.model_dump_json())
            return

        await save_state(redis_client, device, slug, after_hint(state, level))
        await save_hint(
            factory,
            hint_id=hint_id,
            device=device,
            slug=slug,
            level=level,
            text=result.text,
            decision=result.decision,
            rewrite_count=result.rewrite_count,
        )
        for chunk in chunk_text(result.text):
            yield sse("token", TokenEvent(text=chunk).model_dump_json())
        done = DoneEvent(hint_id=hint_id, level=level, supported=info.supported)
        yield sse("done", done.model_dump_json())

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/hint/{hint_id}/rating", status_code=204)
async def post_rating(
    hint_id: uuid.UUID,
    body: RatingRequest,
    device_id: str = Depends(require_device),
    factory: SessionFactory = Depends(get_session_factory),
) -> Response:
    if not await rate_hint(factory, hint_id, device_hash(device_id), body.rating):
        raise HTTPException(status_code=404, detail="hint not found")
    return Response(status_code=204)
