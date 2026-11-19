import hashlib
import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.prompts import load_prompt, render
from app.models import Hint
from app.reference.queue import Enqueue
from app.reference.store import latest_reference, upsert_problem
from app.reference.supported import is_supported
from app.schemas.hint import HintRequest

logger = logging.getLogger("aporia.hint")

CHUNK_CHARS = 20
SessionFactory = async_sessionmaker[AsyncSession]


def device_hash(device_id: str) -> str:
    return hashlib.sha256(device_id.encode()).hexdigest()


def chunk_text(text: str, size: int = CHUNK_CHARS) -> list[str]:
    return [text[i : i + size] for i in range(0, len(text), size)] or [""]


def build_messages(
    req: HintRequest, level: int, feedback: str | None = None
) -> list[dict[str, str]]:
    """Level prompt with the student's data filled in. `feedback` is the leak-guard rejection."""
    system, user_template = load_prompt(f"hint_l{level}_v1")
    user = render(
        user_template,
        {
            "title": req.problem.title,
            "difficulty": req.problem.difficulty,
            "tags": ", ".join(req.problem.tags),
            "content_text": req.problem.content_text,
            "language": req.language,
            "code": req.code,
            "student_message": req.student_message or "",
            "feedback": feedback or "",
        },
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


@dataclass(frozen=True)
class ProblemInfo:
    supported: bool
    reference_source: str | None  # only a verified reference is ever used


async def lookup_problem(
    factory: SessionFactory, enqueue: Enqueue, req: HintRequest
) -> ProblemInfo:
    """Records the problem, finds its verified reference, and enqueues a build if none exists.

    Any database or queue problem degrades to prompt-only hints; it never fails the request.
    """
    payload = req.problem.model_dump()
    try:
        async with factory() as session:
            row = await upsert_problem(session, payload)
            reference = await latest_reference(session, row.slug)
            await session.commit()
            supported = row.supported
            verified = reference if reference and reference.status == "verified" else None
            source = verified.module_source if verified else None
        if reference is None and supported:
            await enqueue(req.problem.slug, payload)
        return ProblemInfo(supported, source)
    except Exception as exc:  # noqa: BLE001
        logger.warning("problem lookup failed (%s); using prompt-only hints", type(exc).__name__)
        return ProblemInfo(is_supported(req.problem.meta)[0], None)


async def save_hint(
    factory: SessionFactory,
    *,
    hint_id: str,
    device: str,
    slug: str,
    level: int,
    text: str,
    decision: dict[str, Any],
    rewrite_count: int,
) -> None:
    try:
        async with factory() as session:
            session.add(
                Hint(
                    id=uuid.UUID(hint_id),
                    device_hash=device,
                    problem_slug=slug,
                    level=level,
                    text=text,
                    guard_decision=decision,
                    rewrite_count=rewrite_count,
                )
            )
            await session.commit()
    except Exception as exc:  # noqa: BLE001
        logger.warning("could not store hint: %s", type(exc).__name__)


async def rate_hint(factory: SessionFactory, hint_id: uuid.UUID, device: str, rating: int) -> bool:
    """Sets the rating if the hint belongs to this device. Returns whether a row was updated."""
    async with factory() as session:
        result = await session.execute(
            update(Hint).where(Hint.id == hint_id, Hint.device_hash == device).values(rating=rating)
        )
        await session.commit()
        return bool(getattr(result, "rowcount", 0))
