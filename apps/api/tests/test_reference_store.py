from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.config import reset_settings
from app.main import app
from app.models import Problem, ReferenceSolution, TestCase
from app.reference.queue import get_enqueue
from app.reference.store import latest_reference, save_result, upsert_problem, verified_reference
from app.sandbox.base import SandboxError
from app.sandbox.fake import FakeRunner
from app.worker import build_reference_job
from tests.support.modules import (
    GOOD_MODULE,
    LINKED_PROBLEM,
    PAIR_PROBLEM,
    analysis_reply,
    fenced,
)
from tests.support.subprocess_runner import SubprocessRunner
from tests.test_reference import ScriptedLLM


async def test_upsert_problem_stores_no_statement_text(db_session_factory) -> None:
    async with db_session_factory() as session:
        row = await upsert_problem(session, PAIR_PROBLEM)
        assert row.supported is True and row.tags == ["Array", "Hash Table"]
        await upsert_problem(session, {**PAIR_PROBLEM, "title": "Renamed"})
        await upsert_problem(session, LINKED_PROBLEM)
        await session.commit()
        assert (await session.get(Problem, "pair-count")).title == "Renamed"  # type: ignore[union-attr]
        assert (await session.get(Problem, "list-thing")).supported is False  # type: ignore[union-attr]
    assert not hasattr(Problem, "content_text")


async def test_worker_job_verifies_and_persists(db_session_factory) -> None:
    llm = ScriptedLLM([analysis_reply(), fenced(GOOD_MODULE)])
    ctx: dict[str, Any] = {
        "runner": SubprocessRunner(),
        "llm": llm,
        "session_factory": db_session_factory,
    }
    assert await build_reference_job(ctx, "pair-count", PAIR_PROBLEM) == "verified"
    async with db_session_factory() as session:
        ref = await verified_reference(session, "pair-count")
        assert ref is not None and ref.verified_cases >= 300 and ref.comparison == "exact"
        cases = await session.scalar(select(func.count()).select_from(TestCase))
        assert cases == 2 + ref.verified_cases
        sources = set((await session.scalars(select(TestCase.source))).all())
        assert sources == {"example", "generated"}


async def test_worker_job_unsupported_and_mock_and_infra(db_session_factory) -> None:
    base: dict[str, Any] = {"runner": FakeRunner(), "session_factory": db_session_factory}
    assert (
        await build_reference_job({**base, "llm": ScriptedLLM([])}, "list-thing", LINKED_PROBLEM)
        == "unsupported"
    )
    # mock mode (APORIA_LLM_MOCK=1 in tests) without an injected llm builds nothing
    out = await build_reference_job(base, "pair-count", PAIR_PROBLEM)
    assert out.startswith("skipped")
    # infrastructure failures are not stored as a permanent "failed"
    llm = ScriptedLLM([analysis_reply(), fenced(GOOD_MODULE)])
    ctx = {
        "runner": FakeRunner([SandboxError("down")]),
        "llm": llm,
        "session_factory": db_session_factory,
    }
    assert (await build_reference_job(ctx, "pair-count", PAIR_PROBLEM)).startswith(
        "infrastructure_error"
    )
    async with db_session_factory() as session:
        assert await latest_reference(session, "pair-count") is None
        assert await session.scalar(select(func.count()).select_from(ReferenceSolution)) == 0


async def test_failed_verification_is_stored_without_cases(db_session_factory) -> None:
    from tests.support.modules import BUGGY_MODULE, EXAMPLES_OK

    llm = ScriptedLLM([analysis_reply(EXAMPLES_OK)] + [fenced(BUGGY_MODULE)] * 3)
    ctx = {"runner": SubprocessRunner(), "llm": llm, "session_factory": db_session_factory}
    assert await build_reference_job(ctx, "pair-count", PAIR_PROBLEM) == "failed"
    async with db_session_factory() as session:
        ref = await latest_reference(session, "pair-count")
        assert ref is not None and ref.status == "failed"
        assert await verified_reference(session, "pair-count") is None
        assert await session.scalar(select(func.count()).select_from(TestCase)) == 0
    assert save_result  # imported API stays covered by the job above


@pytest.fixture
def enqueued() -> list[tuple[str, dict[str, Any]]]:
    calls: list[tuple[str, dict[str, Any]]] = []

    async def fake_enqueue(slug: str, problem: dict[str, Any]) -> bool:
        calls.append((slug, problem))
        return True

    app.dependency_overrides[get_enqueue] = lambda: fake_enqueue
    yield calls
    app.dependency_overrides.pop(get_enqueue, None)


BODY = {
    "title": "Pair Count",
    "difficulty": "Easy",
    "tags": [],
    "content_text": "x",
    "meta": None,
}


async def test_internal_endpoint_open_outside_production(
    client: AsyncClient, enqueued: list[tuple[str, dict[str, Any]]]
) -> None:
    r = await client.post("/v1/internal/reference/pair-count", json={**BODY, "slug": "pair-count"})
    assert r.status_code == 202 and r.json() == {"enqueued": True}
    assert enqueued[0][0] == "pair-count"


async def test_internal_endpoint_requires_token_in_production(
    client: AsyncClient,
    enqueued: list[tuple[str, dict[str, Any]]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APORIA_ENV", "production")
    monkeypatch.setenv("APORIA_INTERNAL_TOKEN", "s3cret")
    reset_settings()
    payload = {**BODY, "slug": "pair-count"}
    assert (await client.post("/v1/internal/reference/x", json=payload)).status_code == 403
    bad = await client.post(
        "/v1/internal/reference/x", json=payload, headers={"X-Aporia-Internal": "nope"}
    )
    assert bad.status_code == 403
    ok = await client.post(
        "/v1/internal/reference/x", json=payload, headers={"X-Aporia-Internal": "s3cret"}
    )
    assert ok.status_code == 202 and len(enqueued) == 1


async def test_internal_endpoint_closed_in_production_without_configured_token(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APORIA_ENV", "production")
    reset_settings()
    r = await client.post(
        "/v1/internal/reference/x",
        json={**BODY, "slug": "x"},
        headers={"X-Aporia-Internal": ""},
    )
    assert r.status_code == 403
