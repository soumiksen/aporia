import logging
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select

from app.api.hint import get_generator, get_retriever
from app.config import Settings, reset_settings
from app.guard.llm_judge import get_judge
from app.guard.safe_hints import safe_hint
from app.hints.cache import cache_key, failing_case_hash, should_bypass
from app.hints.retrieval_context import RetrievalContext
from app.llm import calls
from app.llm.budget import budget_exceeded, day_start, reset_budget_cache
from app.llm.router import group_for_level, router_config
from app.main import app
from app.models import LLMCall
from tests.test_hint_ladder_guard import (
    CLEAN,
    NONE,
    ScriptedGenerator,
    ScriptedJudge,
    ask,
    shown,
)

# ---- routing ----


@pytest.mark.parametrize(
    ("level", "group"), [(1, "fast"), (2, "fast"), (3, "strong"), (4, "strong")]
)
def test_group_for_level(level, group) -> None:
    assert group_for_level(level) == group


def test_router_config_groups_fallbacks_and_params() -> None:
    s = Settings(
        aporia_model_fast="ollama_chat/small",
        aporia_model_strong="ollama_chat/big",
        aporia_model_judge="",  # unset group is simply not routable
        aporia_fallbacks_fast="ollama_chat/b1, ollama_chat/b2",
        aporia_llm_extra_params={"think": False},
        llm_timeout_s=30,
        llm_num_retries=2,
    )
    cfg = router_config(s)
    names = [m["model_name"] for m in cfg["model_list"]]
    assert names == ["fast", "fast_fallback1", "fast_fallback2", "strong"]
    assert cfg["fallbacks"] == [{"fast": ["fast_fallback1", "fast_fallback2"]}]
    assert (cfg["num_retries"], cfg["timeout"]) == (2, 30)
    p = cfg["model_list"][0]["litellm_params"]
    assert p == {"model": "ollama_chat/small", "timeout": 30, "think": False}


# ---- cache keys and bypass rules ----


def test_cache_key_components_and_device_rule() -> None:
    base = cache_key("two-sum", 2, "code", None, "v3")
    assert base == cache_key("two-sum", 2, "code", None, "v3")  # stable
    assert (
        len(
            {
                base,
                cache_key("x", 2, "code", None, "v3"),
                cache_key("two-sum", 3, "code", None, "v3"),
                cache_key("two-sum", 2, "other", None, "v3"),
                cache_key("two-sum", 2, "code", None, "v2"),
                cache_key("two-sum", 2, "code", {"input": [1]}, "v3"),
            }
        )
        == 6
    )
    mine = cache_key("two-sum", 2, "code", None, "v3", device="aaaa")
    other = cache_key("two-sum", 2, "code", None, "v3", device="bbbb")
    assert base != mine != other  # personalised hints are per device
    assert "code" not in base  # the student's code is hashed, never in the key


def test_failing_case_hash_is_order_independent() -> None:
    a = failing_case_hash({"input": [1, 2], "expected": 3, "kind": "wrong_answer"})
    b = failing_case_hash({"kind": "wrong_answer", "expected": 3, "input": [1, 2]})
    assert a == b != failing_case_hash({"input": [1, 3], "expected": 3, "kind": "wrong_answer"})
    assert failing_case_hash(None) == "none"


@pytest.mark.parametrize(
    ("kwargs", "bypass"),
    [
        ({}, False),
        ({"guard_on": False}, True),
        ({"use_rag": False}, True),
        ({"use_memory": False}, True),
        ({"student_message": "why?"}, True),
        ({"student_message": "   "}, False),
        ({"ttl_s": 0}, True),
    ],
)
def test_bypass_rules(kwargs, bypass) -> None:
    args = {"guard_on": True, "use_rag": True, "use_memory": True, "student_message": None,
            "ttl_s": 3600} | kwargs  # fmt: skip
    assert should_bypass(**args) is bypass


# ---- the cache over HTTP ----


@pytest.fixture
def cached_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HINT_CACHE_TTL_S", "3600")
    reset_settings()


@pytest.fixture
def use():
    def install(generator: ScriptedGenerator, judge: ScriptedJudge) -> None:
        app.dependency_overrides[get_generator] = lambda: generator
        app.dependency_overrides[get_judge] = lambda: judge

    yield install
    for dep in (get_generator, get_judge, get_retriever):
        app.dependency_overrides.pop(dep, None)


async def test_identical_request_is_served_from_the_cache(client, cached_env, use) -> None:
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    first = await ask(client, level=1)
    second = await ask(client, level=1)
    assert len(gen.calls) == 1  # the second hint cost no model call
    assert shown(first) == shown(second) == CLEAN
    assert first[-1][1]["hint_id"] != second[-1][1]["hint_id"]  # still its own hint row


async def test_different_code_or_level_is_a_cache_miss(client, cached_env, use) -> None:
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    await ask(client, level=1)
    await ask(client, level=1, code="def pairCount(a, t):\n    return 2")
    await ask(client, level=2)
    assert len(gen.calls) == 3


async def test_student_message_bypasses_the_cache(client, cached_env, use) -> None:
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    await ask(client, level=1, student_message="I think my loop is wrong")
    await ask(client, level=1, student_message="I think my loop is wrong")
    assert len(gen.calls) == 2


class MemoryRetriever:
    async def gather(self, **kw: Any) -> RetrievalContext:
        return RetrievalContext(memory_used=True)

    async def remember(self, **kw: Any) -> None:
        return None


async def test_memory_personalised_hints_are_never_shared_across_devices(
    client, cached_env, use
) -> None:
    app.dependency_overrides[get_retriever] = lambda: MemoryRetriever()
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    await ask(client, level=1, headers={"X-Aporia-Device": "device-A"})
    await ask(client, level=1, headers={"X-Aporia-Device": "device-A"})  # same device: cached
    assert len(gen.calls) == 1
    await ask(client, level=1, headers={"X-Aporia-Device": "device-B"})  # other device: fresh
    assert len(gen.calls) == 2


async def test_without_memory_the_cache_is_shared_across_devices(client, cached_env, use) -> None:
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    await ask(client, level=1, headers={"X-Aporia-Device": "device-A"})
    await ask(client, level=1, headers={"X-Aporia-Device": "device-B"})
    assert len(gen.calls) == 1


async def test_safe_hint_fallbacks_are_not_cached(client, cached_env, use) -> None:
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(RuntimeError("judge down")))  # guard fails -> safe hint
    first = await ask(client, level=1)
    assert shown(first) == safe_hint("pair-count", 1)
    use(gen, ScriptedJudge(NONE))  # judge recovers
    second = await ask(client, level=1)
    assert shown(second) == CLEAN and len(gen.calls) == 2  # the safe hint was not served again


# ---- budget guard ----


async def seed_spend(factory, usd: float, when: datetime | None = None) -> None:
    async with factory() as s:
        s.add(LLMCall(ts=when or datetime.now(UTC), purpose="hint", model="m", cost_usd=usd))
        await s.commit()


async def test_budget_logic(db_session_factory) -> None:
    assert await budget_exceeded(db_session_factory, 0) is False  # off
    await seed_spend(db_session_factory, 0.04)
    await seed_spend(db_session_factory, 5.0, datetime.now(UTC) - timedelta(days=2))  # not today
    assert await budget_exceeded(db_session_factory, 0.05, clock=0.0) is False
    await seed_spend(db_session_factory, 0.02)
    assert await budget_exceeded(db_session_factory, 0.05, clock=1.0) is False  # cached for 30 s
    assert await budget_exceeded(db_session_factory, 0.05, clock=100.0) is True  # 0.06 >= 0.05
    assert day_start().hour == 0 and day_start().tzinfo is UTC


async def test_database_error_does_not_block_hints() -> None:
    reset_budget_cache()

    def broken():
        raise RuntimeError("db down")

    assert await budget_exceeded(broken, 1.0, clock=0.0) is False  # type: ignore[arg-type]


async def test_over_budget_serves_safe_hints_and_warns(
    client, db_session_factory, monkeypatch, use, caplog
) -> None:
    monkeypatch.setenv("APORIA_DAILY_BUDGET_USD", "0.01")
    reset_settings()
    await seed_spend(db_session_factory, 0.5)
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    with caplog.at_level(logging.WARNING, logger="aporia.llm"):
        events = await ask(client, level=1)
    assert shown(events) == safe_hint("pair-count", 1) and gen.calls == []  # no model was called
    assert any("daily LLM budget reached" in r.message for r in caplog.records)
    async with db_session_factory() as s:
        from app.models import Hint

        hint = (await s.scalars(select(Hint))).one()
    assert hint.guard_decision == {"budget": "exceeded", "safe_hint": True}


# ---- the call-recording wrapper ----


async def test_tracked_records_tokens_cost_latency_and_hint_id(llm_records, monkeypatch) -> None:
    monkeypatch.setattr(calls, "cost_of", lambda response: 0.0123)
    token = calls.current_hint_id.set("hint-1")
    try:

        async def call():
            return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=120, completion_tokens=30))

        result = await calls.tracked("hint", "provider/m", call)
    finally:
        calls.current_hint_id.reset(token)
    assert result.usage.prompt_tokens == 120  # the caller still gets its response
    (rec,) = llm_records
    assert (rec.purpose, rec.model, rec.input_tokens, rec.output_tokens) == (
        "hint",
        "provider/m",
        120,
        30,
    )
    assert rec.cost_usd == 0.0123 and rec.latency_ms >= 0 and rec.hint_id == "hint-1"


async def test_tracked_supports_instructor_pairs(llm_records) -> None:
    async def call():
        return ("parsed", {"usage": {"prompt_tokens": 7, "completion_tokens": 3}})

    parsed, _ = await calls.tracked("guard_judge", "m", call, response_of=lambda pair: pair[1])
    assert parsed == "parsed"
    assert (llm_records[0].input_tokens, llm_records[0].output_tokens) == (7, 3)


async def test_failed_calls_are_not_recorded_and_recording_errors_are_swallowed(
    llm_records,
) -> None:
    async def boom():
        raise RuntimeError("provider down")

    with pytest.raises(RuntimeError):
        await calls.tracked("hint", "m", boom)
    assert llm_records == []

    async def bad_writer(rec):
        raise OSError("db down")

    calls.set_writer(bad_writer)

    async def ok():
        return SimpleNamespace(usage=None)

    assert (await calls.tracked("hint", "m", ok)).usage is None  # bookkeeping never fails a call


async def test_accumulator_and_hooks_see_every_record(llm_records) -> None:
    seen: list[float] = []
    calls.add_hook(lambda rec: seen.append(rec.cost_usd))
    bucket: list[calls.CallRecord] = []
    token = calls.accumulator.set(bucket)
    try:
        await calls.record(calls.CallRecord("hint", "m", 1, 1, 0.5, 10))
        await calls.record(calls.CallRecord("hint", "m", 1, 1, 0.25, 10))
    finally:
        calls.accumulator.reset(token)
    assert sum(r.cost_usd for r in bucket) == 0.75 and 0.5 in seen
    calls._hooks.clear()  # noqa: SLF001


def test_usage_and_cost_helpers_are_forgiving() -> None:
    assert calls.usage_of(SimpleNamespace()) == (0, 0)
    assert calls.usage_of({"usage": {"prompt_tokens": 2, "completion_tokens": 5}}) == (2, 5)
    assert calls.cost_of(object()) == 0.0  # unknown model prices (local models) cost nothing


async def test_llm_calls_row_round_trip(db_session_factory) -> None:
    async with db_session_factory() as s:
        s.add(LLMCall(purpose="hint", model="m", input_tokens=5, output_tokens=2, cost_usd=0.001,
                      latency_ms=40))  # fmt: skip
        await s.commit()
    async with db_session_factory() as s:
        row = (await s.scalars(select(LLMCall))).one()
    assert (row.purpose, row.input_tokens, row.cost_usd, row.hint_id) == ("hint", 5, 0.001, None)
