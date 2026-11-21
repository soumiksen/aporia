"""The learner model: per-concept mastery (BKT) and past mistakes, keyed by device hash.

Stores concept ids, one-sentence descriptions and embeddings. Never code.
"""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.learner.bkt import DEFAULT_PARAMS, BKTParams
from app.learner.bkt import update as bkt_update
from app.models import ConceptMastery, Mistake, ProblemSummary
from app.rag.embedder import Embedder

ACCEPTED = "Accepted"
MIN_OBS_FOR_WEAK = 2


def is_correct(verdict: str) -> bool:
    return verdict.strip().lower() == ACCEPTED.lower()


async def problem_concepts(session: AsyncSession, slug: str) -> list[str]:
    row = await session.get(ProblemSummary, slug)
    return list(row.concepts or []) if row else []


async def record_attempt(
    session: AsyncSession,
    device_hash: str,
    slug: str,
    verdict: str,
    params: BKTParams = DEFAULT_PARAMS,
) -> dict[str, float]:
    """Updates mastery of each concept of the problem ("Accepted" = correct, anything else =
    incorrect). An accepted attempt also resolves this device's open mistakes on the problem.
    Returns the new p_known per concept."""
    correct = is_correct(verdict)
    updated: dict[str, float] = {}
    for concept in await problem_concepts(session, slug):
        row = await session.get(ConceptMastery, (device_hash, concept))
        if row is None:
            row = ConceptMastery(
                device_hash=device_hash, concept_slug=concept, p_known=params.p_init, n_obs=0
            )
            session.add(row)
        row.p_known = bkt_update(row.p_known, correct, params)
        row.n_obs = (row.n_obs or 0) + 1
        row.updated_at = datetime.now(UTC)
        updated[concept] = row.p_known
    if correct:
        await session.execute(
            update(Mistake)
            .where(Mistake.device_hash == device_hash, Mistake.problem_slug == slug)
            .values(resolved=True)
        )
    await session.commit()
    return updated


async def record_mistake(
    session: AsyncSession,
    embedder: Embedder,
    device_hash: str,
    slug: str,
    concept: str,
    description: str,
) -> Mistake | None:
    """Stores one mistake with its embedding; an identical open one is not stored twice."""
    duplicate = await session.scalar(
        select(Mistake.id).where(
            Mistake.device_hash == device_hash,
            Mistake.problem_slug == slug,
            Mistake.description == description,
            Mistake.resolved.is_(False),
        )
    )
    if duplicate is not None:
        return None
    vector = (await embedder.embed([description]))[0]
    row = Mistake(
        device_hash=device_hash,
        problem_slug=slug,
        concept_slug=concept,
        description=description,
        embedding=vector,
    )
    session.add(row)
    await session.commit()
    return row


async def weak_concepts(
    session: AsyncSession, device_hash: str, k: int = 3
) -> list[tuple[str, float]]:
    """The k concepts with the lowest p_known among those observed at least twice."""
    rows = (
        await session.execute(
            select(ConceptMastery.concept_slug, ConceptMastery.p_known)
            .where(
                ConceptMastery.device_hash == device_hash,
                ConceptMastery.n_obs >= MIN_OBS_FOR_WEAK,
            )
            .order_by(ConceptMastery.p_known.asc(), ConceptMastery.concept_slug.asc())
            .limit(k)
        )
    ).all()
    return [(r[0], float(r[1])) for r in rows]


def overlapping(weak: Sequence[tuple[str, float]], concepts: Sequence[str]) -> list[str]:
    wanted = set(concepts)
    return [c for c, _ in weak if c in wanted]
