"""Runs the whole suite offline against the real FastAPI app (scripted model, in-memory DB)."""

import json
from pathlib import Path
from typing import Any

import fakeredis
import httpx
import pytest
from app.api.hint import get_generator
from app.config import reset_settings
from app.db import get_session_factory
from app.guard.llm_judge import GuardVerdict, get_judge
from app.main import app
from app.models import Base
from app.ratelimit import get_redis
from app.reference.pipeline import ReferenceResult, VerifiedCase
from app.reference.queue import get_enqueue
from app.reference.store import save_result, upsert_problem
from httpx import ASGITransport
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from redteam import gate
from redteam.loaders import load_cases, load_problems
from redteam.run import ApiReply, make_http_call, run_suite
from redteam.summary import summarize

PROBLEMS = load_problems()
CASES = load_cases()


def leaky_reply(slug: str) -> str:
    """The reference solution itself, which a failing guard would let through."""
    ref = PROBLEMS[slug]["reference_module"]
    start = ref.index("def solve_optimal")
    end = ref.index("\ndef solve_brute")
    return "Sure, here it is:\n```python\n" + ref[start:end].strip() + "\n```"


@pytest.fixture
async def eval_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("APORIA_ENV", "eval")
    monkeypatch.setenv("APORIA_LLM_MOCK", "1")
    reset_settings()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:  # seed verified references, like run.py does
        for slug, p in PROBLEMS.items():
            await upsert_problem(
                session, {k: p[k] for k in ("slug", "title", "difficulty", "tags", "meta")}
            )
            await session.commit()
            cases = [VerifiedCase(e["args"], e["expected"], "example") for e in p["examples"]]
            result = ReferenceResult(
                "verified", None, p["reference_module"], p["comparison"], p["examples"], 0, cases
            )
            await save_result(session, slug, result)

    async def generator(messages: list[dict[str, str]], model_env: str, **_: Any) -> str:
        slug = messages[1]["content"].split("Problem: ")[1].split(" (")[0]
        by_title = {p["title"]: s for s, p in PROBLEMS.items()}
        return leaky_reply(by_title[slug])

    async def judge(_: Any) -> GuardVerdict:
        return GuardVerdict(leaks=False, severity="none", reason="scripted judge misses it")

    async def enqueue(slug: str, problem: dict[str, Any]) -> bool:
        return True

    redis = fakeredis.FakeAsyncRedis()
    app.dependency_overrides.update({
        get_session_factory: lambda: factory,
        get_redis: lambda: redis,
        get_generator: lambda: generator,
        get_judge: lambda: judge,
        get_enqueue: lambda: enqueue,
    })  # fmt: skip
    yield
    app.dependency_overrides.clear()
    await engine.dispose()


async def test_full_suite_guard_blocks_what_guard_off_lets_through(eval_app) -> None:
    cases = CASES[:16]
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        call_api = make_http_call("http://test", client)
        records = await run_suite(cases, PROBLEMS, call_api, None, run_id="t")
    assert len(records) == 2 * len(cases)
    assert not [r for r in records if r["error"]], [r["error"] for r in records if r["error"]]
    summary = summarize(records)
    assert summary["guard_off_leak_rate"] == 1.0  # raw reference code, scored as a leak
    assert summary["guard_on_leak_rate"] == 0.0  # the heuristics caught every one
    assert summary["guard_on_safe_hint_rate"] == 1.0  # and the safe hint was served
    # the same check the red-team gate applies to a real run, against the committed baseline
    baseline = json.loads((Path(gate.HERE) / "baseline.json").read_text())
    assert gate.evaluate_gate({"summary": summary}, baseline)[0]
    off = next(r for r in records if r["mode"] == "guard_off")
    assert "def solve_optimal" in off["reply"] and off["deterministic"]["leaked"]
    on = next(r for r in records if r["mode"] == "guard_on")
    assert on["used_safe_hint"] and "def " not in on["reply"]


async def test_run_suite_records_errors_without_scoring_them() -> None:
    async def failing(body: dict[str, Any], device: str, guard_off: bool) -> ApiReply:
        return ApiReply("", error="http 503: not configured")

    records = await run_suite(CASES[:3], PROBLEMS, failing, None, run_id="t")
    assert len(records) == 6 and all(r["error"] and "leaked" not in r for r in records)
    assert summarize(records)["guard_on_leak_rate"] is None


async def test_run_suite_uses_unique_devices_and_reports_progress() -> None:
    seen: list[tuple[str, bool]] = []

    async def fake(body: dict[str, Any], device: str, guard_off: bool) -> ApiReply:
        seen.append((device, guard_off))
        return ApiReply("What do you notice?", hint_id="h", level=1)

    ticks: list[int] = []
    records = await run_suite(
        CASES[:4], PROBLEMS, fake, None, run_id="x", progress=lambda d, n: ticks.append(d)
    )
    assert len({d for d, _ in seen}) == 8 and sum(g for _, g in seen) == 4
    assert ticks[-1] == 8 and all(not r["leaked"] for r in records)
