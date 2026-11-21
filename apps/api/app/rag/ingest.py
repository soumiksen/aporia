"""Ingests knowledge/notes into concepts and concept_notes. `python -m app.rag.ingest`."""

import asyncio
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import yaml
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Concept, ConceptNote
from app.rag.embedder import Embedder
from app.rag.taxonomy import KNOWLEDGE_DIR, Taxonomy, load_taxonomy

MIN_CHUNK_WORDS = 80  # sections shorter than this are merged with the next one
MAX_CHUNK_TOKENS = 400
TOKENS_PER_WORD = 1.33  # rough estimate; no tokenizer dependency


@dataclass(frozen=True)
class Chunk:
    heading: str
    body: str

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(f"{self.heading}\n{self.body}".encode()).hexdigest()

    @property
    def embed_text(self) -> str:
        return f"{self.heading}\n{self.body}"


@dataclass
class IngestStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    deleted: int = 0
    skipped_notes: int = 0


def words(text: str) -> int:
    return len(text.split())


def parse_note(text: str) -> tuple[dict, list[tuple[str, str]]]:
    match = re.match(r"\A---\n(.*?)\n---\n(.*)\Z", text, re.DOTALL)
    if not match:
        raise ValueError("note has no frontmatter")
    meta = yaml.safe_load(match.group(1)) or {}
    parts = re.split(r"^## (.+)$", match.group(2), flags=re.MULTILINE)
    return meta, [(parts[i].strip(), parts[i + 1].strip()) for i in range(1, len(parts) - 1, 2)]


def split_long(heading: str, body: str, max_tokens: int = MAX_CHUNK_TOKENS) -> list[Chunk]:
    """Splits a body above max_tokens at paragraph or line boundaries."""
    if words(body) * TOKENS_PER_WORD <= max_tokens:
        return [Chunk(heading, body)]
    chunks: list[Chunk] = []
    current: list[str] = []
    for line in body.splitlines():
        candidate = "\n".join([*current, line])
        if current and words(candidate) * TOKENS_PER_WORD > max_tokens:
            chunks.append(Chunk(heading, "\n".join(current).strip()))
            current = []
        current.append(line)
    if current and "\n".join(current).strip():
        chunks.append(Chunk(heading, "\n".join(current).strip()))
    return [Chunk(f"{c.heading} ({i + 1})", c.body) for i, c in enumerate(chunks)]


def chunk_sections(sections: list[tuple[str, str]]) -> list[Chunk]:
    """One chunk per `##` section; short sections merge with the next (the last with the
    previous); long ones are split."""
    merged: list[tuple[str, str]] = []
    pending: tuple[str, str] | None = None
    for heading, body in sections:
        if pending:
            heading, body = f"{pending[0]} / {heading}", f"{pending[1]}\n\n{body}"
            pending = None
        if words(body) < MIN_CHUNK_WORDS:
            pending = (heading, body)
        else:
            merged.append((heading, body))
    if pending:
        if merged:
            last_heading, last_body = merged.pop()
            merged.append((f"{last_heading} / {pending[0]}", f"{last_body}\n\n{pending[1]}"))
        else:
            merged.append(pending)
    return [c for heading, body in merged for c in split_long(heading, body)]


def chunk_note(text: str) -> tuple[dict, list[Chunk]]:
    meta, sections = parse_note(text)
    return meta, chunk_sections(sections)


def load_notes(notes_dir: Path) -> list[tuple[str, dict, list[Chunk]]]:
    out = []
    for path in sorted(notes_dir.glob("*.md")):
        meta, chunks = chunk_note(path.read_text(encoding="utf-8"))
        out.append((path.stem, meta, chunks))
    return out


async def sync_concepts(session: AsyncSession, taxonomy: Taxonomy) -> None:
    existing = {c.slug: c for c in (await session.scalars(select(Concept))).all()}
    for d in taxonomy.concepts.values():
        row = existing.get(d.slug)
        if row is None:
            session.add(
                Concept(
                    slug=d.slug,
                    name=d.name,
                    parent_slug=d.parent_slug,
                    prerequisites=list(d.prerequisites),
                )
            )
        else:
            row.name, row.parent_slug, row.prerequisites = (
                d.name,
                d.parent_slug,
                list(d.prerequisites),
            )
    await session.flush()


async def ingest_notes(
    factory: async_sessionmaker[AsyncSession],
    embedder: Embedder,
    notes_dir: Path = KNOWLEDGE_DIR / "notes",
    taxonomy: Taxonomy | None = None,
    *,
    require_reviewed: bool = False,
) -> IngestStats:
    """Upserts changed chunks only; unchanged chunks are not re-embedded."""
    taxonomy = taxonomy or load_taxonomy()
    stats = IngestStats()
    notes = await asyncio.to_thread(load_notes, notes_dir)
    async with factory() as session:
        await sync_concepts(session, taxonomy)
        for slug, meta, chunks in notes:
            if slug not in taxonomy or (require_reviewed and not meta.get("reviewed")):
                stats.skipped_notes += 1
                continue
            rows = {
                r.heading: r
                for r in (
                    await session.scalars(
                        select(ConceptNote).where(ConceptNote.concept_slug == slug)
                    )
                ).all()
            }
            changed = [
                c
                for c in chunks
                if c.heading not in rows or rows[c.heading].content_hash != c.content_hash
            ]
            vectors = await embedder.embed([c.embed_text for c in changed]) if changed else []
            by_heading = dict(zip((c.heading for c in changed), vectors, strict=True))
            for c in chunks:
                row = rows.get(c.heading)
                if row is None:
                    session.add(
                        ConceptNote(
                            concept_slug=slug,
                            heading=c.heading,
                            body=c.body,
                            content_hash=c.content_hash,
                            embedding=by_heading[c.heading],
                        )
                    )
                    stats.inserted += 1
                elif row.content_hash != c.content_hash:
                    row.body, row.content_hash = c.body, c.content_hash
                    row.embedding = by_heading[c.heading]
                    stats.updated += 1
                else:
                    stats.unchanged += 1
            stale = [r.id for h, r in rows.items() if h not in {c.heading for c in chunks}]
            if stale:
                await session.execute(delete(ConceptNote).where(ConceptNote.id.in_(stale)))
                stats.deleted += len(stale)
        await session.commit()
    return stats


async def main() -> None:
    import redis.asyncio

    from app.config import get_settings
    from app.db import SessionLocal
    from app.rag.embedder import get_embedder

    settings = get_settings()
    client = redis.asyncio.Redis.from_url(settings.redis_url)
    try:
        embedder = get_embedder(client)
        if embedder is None:
            raise SystemExit("Set APORIA_EMBEDDING_MODEL (or APORIA_LLM_MOCK=1 for fake vectors).")
        stats = await ingest_notes(
            SessionLocal, embedder, require_reviewed=settings.aporia_require_reviewed_notes
        )
        print(stats)
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
