import hashlib
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from app.llm.gateway import LLMConfigError, ensure_configured, stream_completion
from app.llm.prompts import load_prompt, render
from app.ratelimit import enforce_rate_limit
from app.schemas.hint import DoneEvent, ErrorEvent, HintRequest, TokenEvent

router = APIRouter(prefix="/v1")
logger = logging.getLogger("aporia.hint")

MAX_CODE_CHARS = 50_000
MAX_CONTENT_CHARS = 50_000
MAX_MESSAGE_CHARS = 2_000
MAX_BODY_BYTES = 256_000
SERVED_LEVEL = 1  # Stage 1 implements only level 1


def sse(event: str, payload: str) -> str:
    return f"event: {event}\ndata: {payload}\n\n"


def check_limits(req: HintRequest) -> None:
    if len(req.code) > MAX_CODE_CHARS:
        raise HTTPException(status_code=413, detail=f"code exceeds {MAX_CODE_CHARS} characters")
    if len(req.problem.content_text) > MAX_CONTENT_CHARS:
        raise HTTPException(status_code=413, detail="problem content_text is too long")
    if req.student_message and len(req.student_message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail="student_message is too long")


def build_messages(req: HintRequest) -> list[dict[str, str]]:
    system, user_template = load_prompt("hint_v0")
    user = render(
        user_template,
        {
            "title": req.problem.title,
            "difficulty": req.problem.difficulty,
            "tags": ", ".join(req.problem.tags),
            "content_text": req.problem.content_text,
            "language": req.language,
            "code": req.code,
        },
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def hint_events(req: HintRequest, hint_id: str, device_id: str) -> AsyncIterator[str]:
    metadata = {
        "hint_id": hint_id,
        "level": SERVED_LEVEL,
        "device_hash": hashlib.sha256(device_id.encode()).hexdigest(),
    }
    try:
        async for text in stream_completion(
            build_messages(req), "APORIA_MODEL_FAST", metadata=metadata
        ):
            yield sse("token", TokenEvent(text=text).model_dump_json())
        yield sse("done", DoneEvent(hint_id=hint_id, level=SERVED_LEVEL).model_dump_json())
    except Exception as exc:  # noqa: BLE001 - never leak provider details or student code
        logger.error("hint generation failed: %s", type(exc).__name__)
        err = ErrorEvent(code="llm_error", message="Could not generate a hint. Please try again.")
        yield sse("error", err.model_dump_json())


@router.post("/hint")
async def post_hint(
    request: Request,
    body: HintRequest,
    device_id: str = Depends(enforce_rate_limit),
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
    logger.info(
        "hint requested slug=%s level=%d hint_id=%s", body.problem.slug, body.level, hint_id
    )
    return StreamingResponse(
        hint_events(body, hint_id, device_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
