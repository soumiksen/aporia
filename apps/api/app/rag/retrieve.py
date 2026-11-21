"""Hybrid retrieval: Postgres full-text + pgvector, fused with RRF, optionally reranked."""

import re
from collections.abc import Hashable, Sequence
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import ARRAY, String, bindparam, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ConceptNote, ProblemSummary
from app.rag.constants import RRF_K
from app.rag.embedder import Embedder
from app.rag.rerank import Reranker, get_reranker

Kind = Literal["notes", "problems"]
Mode = Literal["vector", "fts", "hybrid", "hybrid_rerank"]
MODES: tuple[Mode, ...] = ("vector", "fts", "hybrid", "hybrid_rerank")
CANDIDATES = 20  # per ranking, before fusion


@dataclass(frozen=True)
class Hit:
    kind: Kind
    slug: str  # concept slug for notes, problem slug for problems
    text: str
    heading: str | None = None  # notes only
    concepts: list[str] = field(default_factory=list)  # problems only
    score: float = 0.0

    @property
    def key(self) -> str:
        return f"{self.slug}#{self.heading}" if self.kind == "notes" else self.slug


def rrf_fuse[K: Hashable](rankings: Sequence[Sequence[K]], k: int = RRF_K) -> list[tuple[K, float]]:
    """Reciprocal Rank Fusion: score(d) = sum over rankings of 1 / (k + rank), rank from 1.

    Pure. Ties are broken by the best rank any list gave the item, then by first appearance.
    Empty or one-sided lists are fine. Duplicates within one list count once (their best rank).
    """
    scores: dict[K, float] = {}
    best_rank: dict[K, int] = {}
    order: dict[K, int] = {}
    for ranking in rankings:
        seen: set[K] = set()
        for rank, item in enumerate(ranking, start=1):
            if item in seen:
                continue
            seen.add(item)
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
            best_rank[item] = min(best_rank.get(item, rank), rank)
            order.setdefault(item, len(order))
    return sorted(scores.items(), key=lambda kv: (-kv[1], best_rank[kv[0]], order[kv[0]]))


def fts_query(text: str) -> str:
    """Natural-language text as a websearch query with OR between words, so a long question
    matches on any shared term (websearch_to_tsquery ANDs words by default)."""
    words = re.findall(r"[A-Za-z0-9]+", text.lower())
    return " or ".join(dict.fromkeys(words))


def _entity(kind: Kind):
    return ConceptNote if kind == "notes" else ProblemSummary


def _filters(kind: Kind, concepts: Sequence[str] | None, exclude_slug: str | None):
    conds = []
    if kind == "notes" and concepts:
        conds.append(ConceptNote.concept_slug.in_(list(concepts)))
    if kind == "problems":
        if concepts:
            arr = bindparam("concepts", list(concepts), type_=ARRAY(String))
            conds.append(func.jsonb_exists_any(ProblemSummary.concepts, arr))
        if exclude_slug:
            conds.append(ProblemSummary.slug != exclude_slug)
        conds.append(ProblemSummary.embedding.is_not(None))
    return conds


async def fts_search(
    session: AsyncSession,
    query: str,
    kind: Kind,
    limit: int = CANDIDATES,
    concepts: Sequence[str] | None = None,
    exclude_slug: str | None = None,
) -> list[Hit]:
    q = fts_query(query)
    if not q:
        return []
    entity = _entity(kind)
    tsv = literal_column(f"{entity.__tablename__}.tsv")
    tsq = func.websearch_to_tsquery("english", q)
    stmt = (
        select(entity, func.ts_rank_cd(tsv, tsq).label("score"))
        .where(tsv.op("@@")(tsq), *_filters(kind, concepts, exclude_slug))
        .order_by(literal_column("score").desc(), *_tiebreak(entity))
        .limit(limit)
    )
    return [_hit(kind, row[0], float(row[1])) for row in (await session.execute(stmt)).all()]


async def vector_search(
    session: AsyncSession,
    vector: Sequence[float],
    kind: Kind,
    limit: int = CANDIDATES,
    concepts: Sequence[str] | None = None,
    exclude_slug: str | None = None,
) -> list[Hit]:
    entity = _entity(kind)
    distance = entity.embedding.cosine_distance(list(vector))
    stmt = (
        select(entity, (1 - distance).label("score"))
        .where(entity.embedding.is_not(None), *_filters(kind, concepts, exclude_slug))
        .order_by(distance, *_tiebreak(entity))
        .limit(limit)
    )
    return [_hit(kind, row[0], float(row[1])) for row in (await session.execute(stmt)).all()]


def _tiebreak(entity):
    return (entity.id,) if entity is ConceptNote else (entity.slug,)


def _hit(kind: Kind, row, score: float) -> Hit:
    if kind == "notes":
        return Hit("notes", row.concept_slug, row.body, row.heading, score=score)
    return Hit("problems", row.slug, row.summary, concepts=list(row.concepts or []), score=score)


async def retrieve(
    session: AsyncSession,
    embedder: Embedder,
    query: str,
    kind: Kind,
    k: int = 3,
    mode: Mode = "hybrid",
    *,
    concepts: Sequence[str] | None = None,
    exclude_slug: str | None = None,
    reranker: Reranker | None = None,
) -> list[Hit]:
    """Top-k hits for `query`. `concepts` filters notes by concept and problems by overlap."""
    if mode not in MODES:
        raise ValueError(f"unknown retrieval mode: {mode}")
    pool = max(k, CANDIDATES)
    fts: list[Hit] = []
    vec: list[Hit] = []
    if mode in ("fts", "hybrid", "hybrid_rerank"):
        fts = await fts_search(session, query, kind, pool, concepts, exclude_slug)
    if mode in ("vector", "hybrid", "hybrid_rerank"):
        vector = (await embedder.embed([query]))[0]
        vec = await vector_search(session, vector, kind, pool, concepts, exclude_slug)

    if mode == "fts":
        return fts[:k]
    if mode == "vector":
        return vec[:k]

    by_key = {h.key: h for h in [*fts, *vec]}
    fused = rrf_fuse([[h.key for h in fts], [h.key for h in vec]])
    hits = [
        Hit(h.kind, h.slug, h.text, h.heading, h.concepts, score)
        for key, score in fused
        for h in [by_key[key]]
    ]
    if mode == "hybrid_rerank" and hits:
        candidates = hits[:pool]
        scores = await (reranker or get_reranker()).rerank(query, [h.text for h in candidates])
        ranked = sorted(zip(candidates, scores, strict=True), key=lambda p: -p[1])
        hits = [Hit(h.kind, h.slug, h.text, h.heading, h.concepts, s) for h, s in ranked]
    return hits[:k]
