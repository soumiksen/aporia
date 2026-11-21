from typing import Any

from sqlalchemy import select

from app.models import ProblemSummary
from app.rag.embedder import FakeEmbedder
from app.rag.summarize import (
    RawSummary,
    copies_statement,
    generate_summary,
    summarize_and_store,
)
from app.rag.taxonomy import parse_taxonomy
from app.worker import summarize_problem_job

TAXONOMY = parse_taxonomy(
    {
        "concepts": [
            {"slug": "sliding-window", "name": "Sliding window"},
            {"slug": "two-pointers", "name": "Two pointers"},
        ]
    }
)
STATEMENT = (
    "Given a string s find the length of the longest substring without repeating characters."
)
PROBLEM: dict[str, Any] = {
    "slug": "p1",
    "title": "T",
    "difficulty": "Medium",
    "tags": ["String"],
    "content_text": STATEMENT,
}
GOOD = RawSummary(
    summary="Scan a sequence while tracking a contiguous stretch that stays valid.",
    concepts=["sliding-window"],
)


class Scripted:
    def __init__(self, *replies: RawSummary) -> None:
        self.replies, self.calls = list(replies), []

    async def __call__(self, messages: list[dict[str, str]]) -> RawSummary:
        self.calls.append(messages)
        return self.replies.pop(0)


async def test_valid_first_try() -> None:
    llm = Scripted(GOOD)
    r = await generate_summary(PROBLEM, TAXONOMY, llm)
    assert (r.concepts, r.needs_review) == (["sliding-window"], False) and len(llm.calls) == 1
    system = llm.calls[0][0]["content"]
    assert "sliding-window" in system and "two-pointers" in system


async def test_invalid_slug_then_retry_succeeds() -> None:
    bad = RawSummary(summary="Some words here.", concepts=["made-up"])
    llm = Scripted(bad, GOOD)
    r = await generate_summary(PROBLEM, TAXONOMY, llm)
    assert r.concepts == ["sliding-window"] and not r.needs_review
    assert "unknown concept slugs: made-up" in llm.calls[1][1]["content"]


async def test_double_invalid_marks_needs_review_with_no_concepts() -> None:
    bad = RawSummary(summary="A fine sentence.", concepts=["nope"])
    r = await generate_summary(PROBLEM, TAXONOMY, Scripted(bad, bad))
    assert r.concepts == [] and r.needs_review and r.summary == "A fine sentence."


async def test_copied_statement_is_rejected_and_not_kept() -> None:
    copied = RawSummary(summary=STATEMENT, concepts=["sliding-window"])
    assert copies_statement(STATEMENT, STATEMENT)
    r = await generate_summary(PROBLEM, TAXONOMY, Scripted(copied, copied))
    assert r.needs_review and r.summary == ""  # statement text is never stored


async def test_store_keeps_only_summary_tags_and_vector(db_session_factory) -> None:
    await summarize_and_store(db_session_factory, PROBLEM, TAXONOMY, Scripted(GOOD), FakeEmbedder())
    async with db_session_factory() as s:
        row = (await s.scalars(select(ProblemSummary))).one()
    assert row.concepts == ["sliding-window"] and row.embedding and not row.needs_review
    assert STATEMENT not in row.summary


async def test_job_skips_without_embedder(db_session_factory) -> None:
    out = await summarize_problem_job(
        {
            "session_factory": db_session_factory,
            "summary_llm": Scripted(GOOD),
            "embedder": FakeEmbedder(),
            "taxonomy": TAXONOMY,
        },
        "p1",
        PROBLEM,
    )
    assert out == "ok"


async def test_first_hint_enqueues_summary_once(client, summary_calls, db_session_factory) -> None:
    body = {
        "problem": {
            "slug": "p2",
            "title": "T",
            "difficulty": "Easy",
            "tags": [],
            "content_text": "x",
        },
        "code": "pass",
        "language": "python",
    }
    r = await client.post("/v1/hint", json=body, headers={"X-Aporia-Device": "d1"})
    assert r.status_code == 200 and [c[0] for c in summary_calls] == ["p2"]
    async with db_session_factory() as s:
        s.add(ProblemSummary(slug="p2", summary="x", concepts=[]))
        await s.commit()
    await client.post("/v1/hint", json=body, headers={"X-Aporia-Device": "d1"})
    assert len(summary_calls) == 1  # already has a summary
