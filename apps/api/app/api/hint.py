import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import redis.asyncio
from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.db import get_session_factory
from app.grounding.context import render_for_prompt
from app.grounding.service import ground
from app.guard.cascade import cascade_check, resolve_mode
from app.guard.classifier import get_classifier
from app.guard.guard import (
    GuardDecision,
    GuardedResult,
    flag_disabled,
    guard_enabled,
    guarded_reply,
)
from app.guard.llm_judge import Judge, get_judge
from app.guard.safe_hints import safe_hint
from app.hints.cache import (
    CachedHint,
    cache_key,
    get_cached,
    put_cached,
    should_bypass,
)
from app.hints.ladder import after_hint, next_level, with_attempts
from app.hints.retrieval_context import EMPTY, DbRetriever, RetrievalContext, Retriever
from app.hints.service import (
    SessionFactory,
    attempt_seen,
    build_messages,
    chunk_text,
    device_hash,
    lookup_problem,
    rate_hint,
    save_attempt,
    save_hint,
)
from app.hints.state_store import load_state, save_state
from app.learner.describe import describe_failure
from app.llm.budget import budget_exceeded
from app.llm.calls import current_hint_id
from app.llm.gateway import LLMConfigError, complete, ensure_configured
from app.llm.router import group_for_level, model_env_for_group
from app.rag.embedder import get_embedder
from app.ratelimit import enforce_rate_limit, get_redis, require_device
from app.reference.queue import Enqueue, get_enqueue, get_enqueue_summary
from app.sandbox.base import SandboxRunner
from app.sandbox.provider import get_runner
from app.schemas.hint import (
    DoneEvent,
    ErrorEvent,
    HintRequest,
    RatingRequest,
    Source,
    TokenEvent,
)

router = APIRouter(prefix="/v1")
logger = logging.getLogger("aporia.hint")

MAX_CODE_CHARS = 50_000
MAX_CONTENT_CHARS = 50_000
MAX_MESSAGE_CHARS = 2_000
MAX_BODY_BYTES = 256_000

Generator = Callable[..., Awaitable[str]]


def get_generator() -> Generator:
    return complete


def get_retriever(
    factory: SessionFactory = Depends(get_session_factory),
    redis_client: redis.asyncio.Redis = Depends(get_redis),
) -> Retriever | None:
    """None when RAG is not configured (no embedding model): hints stay prompt-only."""
    embedder = get_embedder(redis_client)
    return DbRetriever(factory, embedder) if embedder else None


def sse(event: str, payload: str) -> str:
    return f"event: {event}\ndata: {payload}\n\n"


def check_limits(req: HintRequest) -> None:
    if len(req.code) > MAX_CODE_CHARS:
        raise HTTPException(status_code=413, detail=f"code exceeds {MAX_CODE_CHARS} characters")
    if len(req.problem.content_text) > MAX_CONTENT_CHARS:
        raise HTTPException(status_code=413, detail="problem content_text is too long")
    if req.student_message and len(req.student_message) > MAX_MESSAGE_CHARS:
        raise HTTPException(status_code=413, detail="student_message is too long")


def _sources(
    result: GuardedResult, context: RetrievalContext, cached: list[dict[str, str]], hit: bool
) -> list[Source]:
    """The "Based on" notes: none for a safe hint, the cached ones on a cache hit."""
    if result.used_safe_hint:
        return []
    return [Source.model_validate(c) for c in cached] if hit else context.sources


@router.post("/hint")
async def post_hint(
    request: Request,
    body: HintRequest,
    device_id: str = Depends(enforce_rate_limit),
    factory: SessionFactory = Depends(get_session_factory),
    redis_client: redis.asyncio.Redis = Depends(get_redis),
    enqueue: Enqueue = Depends(get_enqueue),
    enqueue_summary: Enqueue = Depends(get_enqueue_summary),
    generator: Generator = Depends(get_generator),
    judge: Judge = Depends(get_judge),
    runner: SandboxRunner = Depends(get_runner),
    retriever: Retriever | None = Depends(get_retriever),
    settings: Settings = Depends(get_settings),
    x_aporia_disable_guard: str | None = Header(default=None),
    x_aporia_disable_rag: str | None = Header(default=None),
    x_aporia_disable_memory: str | None = Header(default=None),
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
    current_hint_id.set(hint_id)
    device = device_hash(device_id)
    slug = body.problem.slug
    info = await lookup_problem(factory, enqueue, body, enqueue_summary)

    state = with_attempts(
        await load_state(redis_client, device, slug), body.failed_attempts, body.last_verdict
    )
    level = next_level(state, body.level, body.failed_attempts)
    # Routing: the small model for levels 1 and 2, the strong model for levels 3 and 4.
    model_env = model_env_for_group(group_for_level(level))
    try:
        ensure_configured(model_env)  # type: ignore[arg-type]
    except LLMConfigError as exc:
        logger.error("%s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # Execution grounding (Python, supported problem, verified reference), 12 s total budget. Any
    # failure continues prompt-only: the reply is still generated and still guarded.
    grounding = await ground(
        body.problem.model_dump(),
        body.code,
        body.language,
        info.reference,
        runner,
        total_budget_s=settings.grounding_budget_s,
    )
    grounding_text = render_for_prompt(grounding.context, level)
    failing_case = grounding.facts.as_dict() if grounding.facts else None
    failure_kind = grounding.failure.kind if grounding.failure else None
    guard_on = guard_enabled(settings, x_aporia_disable_guard)
    classifier = get_classifier()
    guard_mode = resolve_mode(settings, classifier)
    # Evaluation-only switches (honoured only when APORIA_ENV=eval).
    use_rag = not flag_disabled(settings, x_aporia_disable_rag)
    use_memory = not flag_disabled(settings, x_aporia_disable_memory)
    failure_text = (
        describe_failure(grounding.failure.kind, grounding.failure.input)
        if grounding.failure
        else None
    )
    context: RetrievalContext = EMPTY
    if retriever and (use_rag or use_memory):
        try:
            context = await retriever.gather(
                level=level,
                slug=slug,
                concepts=info.concepts,
                failure_text=failure_text,
                device=device,
                use_rag=use_rag,
                use_memory=use_memory,
            )
        except Exception as exc:  # noqa: BLE001 - retrieval never blocks a hint
            logger.warning("retrieval failed: %s", type(exc).__name__)
    retrieval_text = context.render()
    metadata: dict[str, Any] = {"hint_id": hint_id, "level": level, "device_hash": device}
    logger.info(
        "hint requested slug=%s level=%d hint_id=%s guard=%s grounding=%s kind=%s ms=%d",
        slug,
        level,
        hint_id,
        guard_on,
        ("error:" + grounding.error) if grounding.error else grounding.attempted,
        failure_kind,
        grounding.elapsed_ms,
    )

    async def generate(feedback: str | None) -> str:
        return await generator(
            build_messages(body, level, feedback, grounding_text, retrieval_text),
            model_env,
            metadata=metadata,
        )

    async def check_draft(draft: str) -> GuardDecision:
        return await cascade_check(
            draft,
            level,
            body.problem,
            info.reference_source,
            judge,
            failing_case,
            context.note_texts,
            mode=guard_mode,
            classifier=classifier,
            summary=info.summary,
        )

    bypass = should_bypass(
        guard_on=guard_on,
        use_rag=use_rag,
        use_memory=use_memory,
        student_message=body.student_message,
        ttl_s=settings.hint_cache_ttl_s,
    )
    # With the student's own learner memory in the prompt the key includes the device.
    key = cache_key(
        slug,
        level,
        body.code,
        failing_case,
        settings.aporia_prompt_version,
        device if context.memory_used else None,
    )

    async def events() -> AsyncIterator[str]:
        current_hint_id.set(hint_id)
        cached = None if bypass else await get_cached(redis_client, key)
        sources = [] if cached is None else cached.sources
        try:
            if await budget_exceeded(factory, settings.aporia_daily_budget_usd):
                result = GuardedResult(
                    safe_hint(slug, level), {"budget": "exceeded", "safe_hint": True}, 0, True
                )
            elif cached is not None:
                result = GuardedResult(
                    cached.text, {**cached.decision, "cache": "hit"}, cached.rewrite_count, False
                )
            elif guard_on:
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

        if not bypass and cached is None and not result.used_safe_hint:
            await put_cached(
                redis_client,
                key,
                CachedHint(
                    result.text,
                    result.decision,
                    result.rewrite_count,
                    [s.model_dump() for s in context.sources],
                ),
                settings.hint_cache_ttl_s,
            )
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
            grounded=grounding.grounded,
            failure_kind=failure_kind,
        )
        new_code = not await attempt_seen(factory, device, slug, body.code)
        await save_attempt(
            factory,
            device=device,
            slug=slug,
            code=body.code,
            verdict=body.last_verdict or failure_kind or "unknown",
            failing_case={"kind": failure_kind, "input": grounding.failure.input}
            if grounding.failure
            else None,
        )
        if retriever:
            verdict = body.last_verdict or ("Wrong Answer" if grounding.failure else None)
            await retriever.remember(
                device=device,
                slug=slug,
                concepts=info.concepts,
                failure_text=failure_text,
                verdict=verdict if new_code else None,  # one BKT observation per distinct code
            )
        for chunk in chunk_text(result.text):
            yield sse("token", TokenEvent(text=chunk).model_dump_json())
        done = DoneEvent(
            hint_id=hint_id,
            level=level,
            supported=info.supported,
            grounded=grounding.grounded,
            failure_kind=failure_kind,
            sources=_sources(result, context, sources, cached is not None),
        )
        yield sse("done", done.model_dump_json())

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/hint/{hint_id}/rating", status_code=204)
@router.post("/hints/{hint_id}/rating", status_code=204)
async def post_rating(
    hint_id: uuid.UUID,
    body: RatingRequest,
    device_id: str = Depends(require_device),
    factory: SessionFactory = Depends(get_session_factory),
) -> Response:
    if not await rate_hint(factory, hint_id, device_hash(device_id), body.rating):
        raise HTTPException(status_code=404, detail="hint not found")
    return Response(status_code=204)
