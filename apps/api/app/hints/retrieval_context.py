"""What the hint generator gets from retrieval and the learner model.

Notes and past mistakes are background for the model; the student never sees them verbatim.
Only the note headings are returned (as "Based on" sources).
"""

import logging
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import get_settings
from app.learner.service import (
    MistakeHit,
    overlapping,
    record_attempt,
    record_mistake,
    similar_mistakes,
    weak_concepts,
)
from app.rag.embedder import Embedder
from app.rag.retrieve import Hit, Mode, retrieve
from app.schemas.hint import Source

logger = logging.getLogger("aporia.rag")

MAX_NOTES = 3
MAX_MISTAKES = 3
MAX_ANALOGOUS = 3


@dataclass
class RetrievalContext:
    notes: list[Hit] = field(default_factory=list)
    mistakes: list[MistakeHit] = field(default_factory=list)
    analogous: list[Hit] = field(default_factory=list)
    memory_used: bool = False  # this student's learner data shaped the prompt

    @property
    def sources(self) -> list[Source]:
        return [Source(type="note", slug=n.slug, heading=n.heading or "") for n in self.notes]

    @property
    def note_texts(self) -> list[str]:
        """Passed to the leak guard to catch a note being quoted as the answer."""
        return [n.text for n in self.notes]

    def render(self) -> str:
        blocks: list[str] = []
        if self.notes:
            lines = [f"[note:{n.slug}#{n.heading}] {n.text}" for n in self.notes]
            blocks.append("<notes>\n" + "\n\n".join(lines) + "\n</notes>")
        if self.mistakes:
            lines = [f"[mistake:{m.id}] ({m.concept}) {m.description}" for m in self.mistakes]
            blocks.append("<past_mistakes>\n" + "\n".join(lines) + "\n</past_mistakes>")
        if self.analogous:
            lines = [
                f"[problem:{p.slug}] ({', '.join(p.concepts)}) {p.text}" for p in self.analogous
            ]
            blocks.append("<analogous_problems>\n" + "\n".join(lines) + "\n</analogous_problems>")
        return "\n\n".join(blocks)


EMPTY = RetrievalContext()


def build_query(
    concepts: Sequence[str], failure_text: str | None, weak_overlap: Sequence[str]
) -> str:
    """Concept slugs of the problem + a short description of the failure (if grounded) + the
    student's weak concepts that overlap the problem."""
    parts = [c.replace("-", " ") for c in [*concepts, *weak_overlap]]
    if failure_text:
        parts.append(failure_text)
    return " ".join(dict.fromkeys(parts))


class Retriever(Protocol):
    async def gather(
        self,
        *,
        level: int,
        slug: str,
        concepts: Sequence[str],
        failure_text: str | None,
        device: str,
        use_rag: bool,
        use_memory: bool,
    ) -> RetrievalContext: ...

    async def remember(
        self,
        *,
        device: str,
        slug: str,
        concepts: Sequence[str],
        failure_text: str | None,
        verdict: str | None,
    ) -> None: ...


class DbRetriever:
    """Retrieval and learner-model access over the database. Each part degrades on its own: a
    failure in one yields nothing for it and never fails the hint."""

    def __init__(self, factory: async_sessionmaker[AsyncSession], embedder: Embedder) -> None:
        self.factory = factory
        self.embedder = embedder

    async def gather(
        self,
        *,
        level: int,
        slug: str,
        concepts: Sequence[str],
        failure_text: str | None,
        device: str,
        use_rag: bool,
        use_memory: bool,
    ) -> RetrievalContext:
        mode: Mode = "hybrid_rerank" if get_settings().aporia_rerank else "hybrid"
        ctx = RetrievalContext()
        async with self.factory() as session:
            weak: list[str] = []
            if use_memory:
                try:
                    weak = overlapping(await weak_concepts(session, device), concepts)
                    ctx.memory_used = bool(weak)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("weak concepts failed: %s", type(exc).__name__)
            query = build_query(concepts, failure_text, weak)
            if not query:
                return ctx
            if use_rag:
                try:
                    ctx.notes = await retrieve(
                        session, self.embedder, query, "notes", MAX_NOTES, mode,
                        concepts=list(concepts) or None,
                    )  # fmt: skip
                    if level == 4 and concepts:
                        ctx.analogous = await retrieve(
                            session, self.embedder, query, "problems", MAX_ANALOGOUS, mode,
                            concepts=list(concepts), exclude_slug=slug,
                        )  # fmt: skip
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    logger.warning("retrieval failed: %s", type(exc).__name__)
            if use_memory:
                try:
                    ctx.mistakes = await similar_mistakes(
                        session, self.embedder, device, failure_text or query, slug, MAX_MISTAKES
                    )
                    ctx.memory_used = ctx.memory_used or bool(ctx.mistakes)
                except Exception as exc:  # noqa: BLE001
                    await session.rollback()
                    logger.warning("mistake recall failed: %s", type(exc).__name__)
        return ctx

    async def remember(
        self,
        *,
        device: str,
        slug: str,
        concepts: Sequence[str],
        failure_text: str | None,
        verdict: str | None,
    ) -> None:
        """Records the mistake (one sentence, no code) and the failed attempt for BKT."""
        try:
            async with self.factory() as session:
                if failure_text and concepts:
                    await record_mistake(
                        session, self.embedder, device, slug, concepts[0], failure_text
                    )
                if verdict:
                    await record_attempt(session, device, slug, verdict)
        except Exception as exc:  # noqa: BLE001
            logger.warning("could not update the learner model: %s", type(exc).__name__)
