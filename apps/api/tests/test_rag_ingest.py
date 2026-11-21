import math
from pathlib import Path

import fakeredis
import pytest
from sqlalchemy import func, select

from app.models import Concept, ConceptNote
from app.rag.constants import EMBED_DIM
from app.rag.embedder import (
    CachedEmbedder,
    EmbeddingError,
    FakeEmbedder,
    LiteLLMEmbedder,
    fit_dimension,
)
from app.rag.ingest import MIN_CHUNK_WORDS, chunk_note, chunk_sections, ingest_notes, split_long
from app.rag.taxonomy import load_taxonomy, parse_taxonomy

NOTE = """---
slug: demo
concept: demo
reviewed: false
---
## Idea
{a}

## When it applies
short bit

## Common mistakes
{b}

## Related concepts
x-y
"""
LONG = "word " * 100


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


async def test_fake_embedder_is_deterministic_normalized_and_lexical() -> None:
    e = FakeEmbedder()
    a, a2, b, c = await e.embed(
        [
            "sliding window shrink",
            "sliding window shrink",
            "window shrink early",
            "binary tree height",
        ]
    )
    assert a == a2 and len(a) == EMBED_DIM
    assert math.isclose(cosine(a, a), 1.0, rel_tol=1e-9)
    assert cosine(a, b) > cosine(a, c)


def test_fit_dimension_pads_and_rejects_longer() -> None:
    v = fit_dimension([1.0, 2.0])
    assert len(v) == EMBED_DIM and v[:3] == [1.0, 2.0, 0.0]
    with pytest.raises(EmbeddingError):
        fit_dimension([0.0] * (EMBED_DIM + 1))


def test_chunking_merges_short_and_keeps_long() -> None:
    _, chunks = chunk_note(NOTE.format(a=LONG, b=LONG))
    headings = [c.heading for c in chunks]
    # "When it applies" (short) merges forward into "Common mistakes"; the short last section
    # ("Related concepts") merges back into the previous chunk.
    assert headings == ["Idea", "When it applies / Common mistakes / Related concepts"]
    assert all(c.content_hash for c in chunks)


def test_short_only_note_is_one_chunk_and_long_is_split() -> None:
    assert len(chunk_sections([("A", "one two"), ("B", "three")])) == 1
    chunks = split_long("Big", "\n".join(["word " * 60] * 8), max_tokens=100)
    assert len(chunks) > 1 and chunks[0].heading == "Big (1)"
    assert MIN_CHUNK_WORDS == 80


@pytest.fixture
def notes_dir(tmp_path: Path) -> Path:
    (tmp_path / "demo.md").write_text(NOTE.format(a=LONG, b=LONG))
    return tmp_path


@pytest.fixture
def demo_taxonomy():
    return parse_taxonomy({"concepts": [{"slug": "demo", "name": "Demo"}]})


async def test_ingest_skips_unchanged_chunks(db_session_factory, notes_dir, demo_taxonomy) -> None:
    emb = FakeEmbedder()
    first = await ingest_notes(db_session_factory, emb, notes_dir, demo_taxonomy)
    assert (first.inserted, first.unchanged) == (2, 0)
    assert sum(len(c) for c in emb.calls) == 2

    again = await ingest_notes(db_session_factory, emb, notes_dir, demo_taxonomy)
    assert (again.inserted, again.updated, again.unchanged) == (0, 0, 2)
    assert sum(len(c) for c in emb.calls) == 2  # nothing was embedded again

    (notes_dir / "demo.md").write_text(NOTE.format(a=LONG + "extra", b=LONG))
    changed = await ingest_notes(db_session_factory, emb, notes_dir, demo_taxonomy)
    assert (changed.updated, changed.unchanged) == (1, 1)
    assert sum(len(c) for c in emb.calls) == 3  # only the changed chunk
    async with db_session_factory() as s:
        assert await s.scalar(select(func.count()).select_from(ConceptNote)) == 2
        assert (await s.scalars(select(Concept))).one().slug == "demo"


async def test_ingest_removes_stale_chunks_and_honours_reviewed(
    db_session_factory, notes_dir, demo_taxonomy
) -> None:
    emb = FakeEmbedder()
    skipped = await ingest_notes(
        db_session_factory, emb, notes_dir, demo_taxonomy, require_reviewed=True
    )
    assert skipped.skipped_notes == 1 and skipped.inserted == 0
    await ingest_notes(db_session_factory, emb, notes_dir, demo_taxonomy)
    (notes_dir / "demo.md").write_text(NOTE.format(a=LONG, b=LONG).replace("## Idea", "## Core"))
    stats = await ingest_notes(db_session_factory, emb, notes_dir, demo_taxonomy)
    assert (stats.inserted, stats.deleted) == (1, 1)


async def test_real_notes_ingest(db_session_factory) -> None:
    stats = await ingest_notes(db_session_factory, FakeEmbedder(), taxonomy=load_taxonomy())
    assert stats.inserted >= 40 and stats.skipped_notes == 0


async def test_cache_hits_skip_the_inner_embedder() -> None:
    inner = FakeEmbedder()
    cached = CachedEmbedder(inner, fakeredis.FakeAsyncRedis())
    first = await cached.embed(["a b", "c d"])
    second = await cached.embed(["c d", "e f"])
    assert second[0] == first[1]
    assert inner.calls == [["a b", "c d"], ["e f"]]
    assert cached.key("x") != CachedEmbedder(inner, fakeredis.FakeAsyncRedis()).key("y")


async def test_litellm_embedder_batches_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    import litellm

    calls: list[int] = []

    async def fake_aembedding(model: str, input: list[str]):
        calls.append(len(input))
        if len(calls) == 1:
            raise RuntimeError("rate limited")

        class R:
            data = [{"index": i, "embedding": [float(i)]} for i in range(len(input))]

        return R

    monkeypatch.setattr(litellm, "aembedding", fake_aembedding)
    sleeps: list[float] = []

    async def no_sleep(s: float) -> None:
        sleeps.append(s)

    emb = LiteLLMEmbedder("some/model", sleep=no_sleep)
    out = await emb.embed([f"t{i}" for i in range(70)])
    assert len(out) == 70 and calls == [64, 64, 6] and sleeps == [1.0]
    assert all(len(v) == EMBED_DIM for v in out)
    with pytest.raises(EmbeddingError):
        LiteLLMEmbedder("")
