import socket
from urllib.parse import urlparse

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.config import get_settings
from app.models import Concept, ConceptNote, Problem, ProblemSummary
from app.rag.embedder import FakeEmbedder
from app.rag.rerank import NoopReranker
from app.rag.retrieve import MODES, fts_query, retrieve, rrf_fuse

# ---- rrf_fuse: hand-computed expectations (k = 60) ----


def test_rrf_two_lists_hand_computed() -> None:
    fused = dict(rrf_fuse([["a", "b", "c"], ["b", "a", "d"]]))
    # a: 1/61 + 1/62, b: 1/62 + 1/61, c: 1/63, d: 1/63
    assert fused["a"] == pytest.approx(1 / 61 + 1 / 62)
    assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
    assert fused["c"] == pytest.approx(1 / 63) and fused["d"] == pytest.approx(1 / 63)


def test_rrf_ties_break_by_best_rank_then_first_appearance() -> None:
    # a and b tie on score; a's best rank is 1, b's is 2... both lists are symmetric here
    assert [k for k, _ in rrf_fuse([["a", "b"], ["b", "a"]])] == ["a", "b"]
    # equal score and equal best rank: first appearance wins
    assert [k for k, _ in rrf_fuse([["x"], ["y"]])] == ["x", "y"]
    # c (rank 3 once) ties d (rank 3 once): order of appearance
    assert [k for k, _ in rrf_fuse([["a", "b", "c"], ["a", "b", "d"]])][2:] == ["c", "d"]


def test_rrf_empty_and_one_sided() -> None:
    assert rrf_fuse([]) == [] and rrf_fuse([[], []]) == []
    assert rrf_fuse([["a", "b"], []]) == [
        ("a", pytest.approx(1 / 61)),
        ("b", pytest.approx(1 / 62)),
    ]
    assert [k for k, _ in rrf_fuse([[], ["z", "y"]])] == ["z", "y"]


def test_rrf_item_in_both_lists_beats_item_in_one() -> None:
    order = [k for k, _ in rrf_fuse([["a", "shared"], ["shared", "b"]])]
    assert order[0] == "shared"


def test_rrf_duplicates_in_one_list_count_once_and_k_is_configurable() -> None:
    assert dict(rrf_fuse([["a", "a"]]))["a"] == pytest.approx(1 / 61)
    assert dict(rrf_fuse([["a"]], k=0))["a"] == pytest.approx(1.0)


def test_fts_query_is_an_or_of_words() -> None:
    assert fts_query("My window shrinks, too early!") == "my or window or shrinks or too or early"
    assert fts_query("  ?! ") == ""


# ---- SQL paths against Postgres (needs `alembic upgrade head`; skipped otherwise) ----


def postgres_reachable() -> bool:
    parsed = urlparse(get_settings().database_url.replace("+asyncpg", ""))
    try:
        with socket.create_connection((parsed.hostname or "localhost", parsed.port or 5432), 0.5):
            return True
    except OSError:
        return False


@pytest.fixture
async def pg():
    if not postgres_reachable():
        pytest.skip("Postgres not reachable")
    engine = create_async_engine(get_settings().database_url)
    try:
        conn = await engine.connect()
    except Exception as exc:  # noqa: BLE001
        await engine.dispose()
        pytest.skip(f"Postgres not usable: {exc}")
    trans = await conn.begin()
    session = AsyncSession(bind=conn, expire_on_commit=False)
    emb = FakeEmbedder()
    try:
        session.add_all([Concept(slug="zz-a", name="A"), Concept(slug="zz-b", name="B")])
        await session.flush()
        docs = [
            ("zz-a", "Idea", "the window shrinks when a duplicate letter enters the substring"),
            ("zz-a", "Mistakes", "forgetting to update the answer before the window moves"),
            ("zz-b", "Idea", "heap keeps the largest values near the top of the structure"),
        ]
        vecs = await emb.embed([d[2] for d in docs])
        for (c, h, b), v in zip(docs, vecs, strict=True):
            session.add(
                ConceptNote(concept_slug=c, heading=h, body=b, content_hash="h", embedding=v)
            )
        for slug, summary, concepts in [
            ("zz-p1", "scan a sequence keeping a contiguous stretch valid", ["zz-a"]),
            ("zz-p2", "keep the best few values using a heap", ["zz-b"]),
            ("zz-p3", "another contiguous stretch with a validity rule", ["zz-a", "zz-b"]),
        ]:
            session.add(Problem(slug=slug, title=slug, difficulty="Easy", tags=[], supported=False))
            await session.flush()
            session.add(
                ProblemSummary(
                    slug=slug,
                    summary=summary,
                    concepts=concepts,
                    embedding=(await emb.embed([summary]))[0],
                )
            )
        await session.flush()
        yield session, emb
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()
        await engine.dispose()


@pytest.mark.db
@pytest.mark.parametrize("mode", MODES)
async def test_notes_modes_find_the_relevant_note(pg, mode) -> None:
    session, emb = pg
    hits = await retrieve(
        session,
        emb,
        "my window shrinks when a duplicate letter shows up",
        "notes",
        2,
        mode,
        concepts=["zz-a", "zz-b"],
        reranker=NoopReranker(),
    )
    assert hits and (hits[0].slug, hits[0].heading) == ("zz-a", "Idea")


@pytest.mark.db
async def test_concept_filter_and_empty_fts(pg) -> None:
    session, emb = pg
    only_b = await retrieve(
        session, emb, "window duplicate letter", "notes", 5, "hybrid", concepts=["zz-b"]
    )
    assert {h.slug for h in only_b} == {"zz-b"}
    assert await retrieve(session, emb, "?!", "notes", 3, "fts", concepts=["zz-a"]) == []


@pytest.mark.db
async def test_problems_overlap_and_exclusion(pg) -> None:
    session, emb = pg
    hits = await retrieve(
        session,
        emb,
        "contiguous stretch validity",
        "problems",
        5,
        "hybrid",
        concepts=["zz-a"],
        exclude_slug="zz-p1",
    )
    slugs = [h.slug for h in hits]
    assert "zz-p1" not in slugs and slugs[0] == "zz-p3" and "zz-p2" not in slugs
    both = await retrieve(session, emb, "heap values", "problems", 5, "vector", concepts=["zz-b"])
    assert {h.slug for h in both} == {"zz-p2", "zz-p3"}
