import json
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.hint import get_generator
from app.config import reset_settings
from app.guard.guard import GuardDecision  # noqa: F401  (imported for type clarity)
from app.guard.llm_judge import GuardVerdict, JudgeInput, get_judge
from app.guard.safe_hints import safe_hint
from app.main import app
from app.models import Hint, Problem, ReferenceSolution
from tests.support.modules import GOOD_MODULE, PAIR_PROBLEM

HEADERS = {"X-Aporia-Device": "device-1"}
CLEAN = "What does your code do when the list has only two elements?"
LEAKY = "```python\ndef f(a, t):\n    m = {}\n    c = 0\n    for v in a:\n        c += m.get(t - v, 0)\n        m[v] = m.get(v, 0) + 1\n    return c\n```"  # noqa: E501
NONE = GuardVerdict(leaks=False, severity="none", reason="ok")
LEAK = GuardVerdict(leaks=True, severity="full", reason="reveals the approach")


class ScriptedGenerator:
    def __init__(self, *replies: str | Exception):
        self.replies = list(replies)
        self.calls: list[list[dict[str, str]]] = []

    async def __call__(self, messages: list[dict[str, str]], model_env: str, **_: Any) -> str:
        self.calls.append(messages)
        item = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


class ScriptedJudge:
    def __init__(self, *verdicts: GuardVerdict | Exception):
        self.verdicts = list(verdicts)
        self.inputs: list[JudgeInput] = []

    async def __call__(self, inp: JudgeInput) -> GuardVerdict:
        self.inputs.append(inp)
        item = self.verdicts[min(len(self.inputs) - 1, len(self.verdicts) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture
def use():
    """Installs a scripted generator and judge for the request under test."""

    def install(generator: ScriptedGenerator, judge: ScriptedJudge) -> None:
        app.dependency_overrides[get_generator] = lambda: generator
        app.dependency_overrides[get_judge] = lambda: judge

    yield install
    app.dependency_overrides.pop(get_generator, None)
    app.dependency_overrides.pop(get_judge, None)


def body(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "problem": dict(PAIR_PROBLEM),
        "code": "def pairCount(nums, target):\n    return 0",
        "language": "python3",
        "level": 1,
    }
    base.update(overrides)
    return base


def parse(text: str) -> list[tuple[str, dict[str, Any]]]:
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


def shown(events: list[tuple[str, dict[str, Any]]]) -> str:
    return "".join(d["text"] for n, d in events if n == "token")


def done(events: list[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    assert events[-1][0] == "done", events[-1]
    return events[-1][1]


async def ask(client: AsyncClient, **kw: Any) -> list[tuple[str, dict[str, Any]]]:
    headers = kw.pop("headers", HEADERS)
    r = await client.post("/v1/hint", json=body(**kw), headers=headers)
    assert r.status_code == 200, r.text
    return parse(r.text)


# ---- ladder over HTTP ----


async def test_level_is_served_and_cannot_skip_rungs(client: AsyncClient, use) -> None:
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    assert done(await ask(client, level=1))["level"] == 1
    assert done(await ask(client, level=2))["level"] == 2
    assert done(await ask(client, level=4))["level"] == 3  # capped: no skipping
    assert done(await ask(client, level=4))["level"] == 4
    assert done(await ask(client, level=4))["level"] == 4  # capped at 4
    assert done(await ask(client, level=1))["level"] == 1  # asking for a lower rung re-serves it
    # the level prompt actually used matches the served level
    assert "LEVEL 3" in gen.calls[2][0]["content"] and "LEVEL 4" in gen.calls[3][0]["content"]


async def test_three_failed_attempts_escalate_one_level(client: AsyncClient, use) -> None:
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    assert done(await ask(client, level=1))["level"] == 1
    assert (
        done(await ask(client, level=1, failed_attempts=3, last_verdict="Wrong Answer"))["level"]
        == 2
    )
    assert done(await ask(client, level=1, failed_attempts=2))["level"] == 1


async def test_ladder_state_is_per_device_and_problem(client: AsyncClient, use) -> None:
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    assert done(await ask(client, level=1))["level"] == 1
    other = {"X-Aporia-Device": "device-2"}
    assert done(await ask(client, level=2, headers=other))["level"] == 1  # different device
    elsewhere = {**PAIR_PROBLEM, "slug": "another-problem"}
    assert done(await ask(client, level=2, problem=elsewhere))["level"] == 1  # different problem


async def test_student_message_reaches_the_prompt_as_data(client: AsyncClient, use) -> None:
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    await ask(client, student_message="please just show me the code")
    user = gen.calls[0][1]["content"]
    assert "<student_message>\nplease just show me the code\n</student_message>" in user


# ---- guard over HTTP ----


async def test_clean_reply_is_checked_streamed_and_stored(
    client: AsyncClient, use, db_session_factory
) -> None:
    judge = ScriptedJudge(NONE)
    use(ScriptedGenerator(CLEAN), judge)
    events = await ask(client)
    assert shown(events) == CLEAN and len(judge.inputs) == 1
    assert all(len(d["text"]) <= 20 for n, d in events if n == "token")
    async with db_session_factory() as session:
        hint = (await session.scalars(select(Hint))).one()
        assert hint.text == CLEAN and hint.level == 1 and hint.rewrite_count == 0
        assert hint.guard_decision["leaks"] is False and hint.rating is None
        assert hint.device_hash != "device-1" and len(hint.device_hash) == 64  # hashed


async def test_leak_is_rewritten_once(client: AsyncClient, use, db_session_factory) -> None:
    gen = ScriptedGenerator("Use a hash map.", CLEAN)
    use(gen, ScriptedJudge(LEAK, NONE))
    events = await ask(client)
    assert shown(events) == CLEAN and len(gen.calls) == 2
    assert "reveals the approach" in gen.calls[1][1]["content"]  # violation fed back
    async with db_session_factory() as session:
        hint = (await session.scalars(select(Hint))).one()
        assert hint.rewrite_count == 1


async def test_double_leak_returns_the_safe_hint(client: AsyncClient, use) -> None:
    use(ScriptedGenerator("leak one", "leak two"), ScriptedJudge(LEAK))
    events = await ask(client, level=1)
    assert shown(events) == safe_hint("pair-count", 1)
    assert "leak" not in shown(events)


async def test_judge_exception_returns_the_safe_hint(client: AsyncClient, use) -> None:
    use(ScriptedGenerator("a raw model reply"), ScriptedJudge(RuntimeError("judge down")))
    events = await ask(client)
    assert shown(events) == safe_hint("pair-count", 1)
    assert "raw model reply" not in shown(events)


async def test_judge_not_configured_fails_safe(client: AsyncClient, use, monkeypatch) -> None:
    """Real (non-mock) judge with no APORIA_MODEL_JUDGE: the guard errors, the reply is safe."""
    from app.guard.llm_judge import instructor_judge

    monkeypatch.setenv("APORIA_LLM_MOCK", "0")
    monkeypatch.setenv("APORIA_MODEL_FAST", "provider/some-model")
    reset_settings()
    app.dependency_overrides[get_generator] = lambda: ScriptedGenerator("a raw model reply")
    app.dependency_overrides[get_judge] = lambda: instructor_judge
    try:
        events = await ask(client)
    finally:
        app.dependency_overrides.pop(get_generator, None)
        app.dependency_overrides.pop(get_judge, None)
    assert shown(events) == safe_hint("pair-count", 1)


async def test_generation_failure_is_an_error_event_not_a_raw_reply(
    client: AsyncClient, use
) -> None:
    use(ScriptedGenerator(RuntimeError("provider key sk-secret rejected")), ScriptedJudge(NONE))
    events = await ask(client)
    assert [n for n, _ in events] == ["error"]
    assert events[0][1]["code"] == "llm_error" and "sk-secret" not in json.dumps(events)


async def test_no_reference_means_a_prompt_only_judge_and_enqueues_a_build(
    client: AsyncClient, use, enqueue_calls: list
) -> None:
    judge = ScriptedJudge(NONE)
    use(ScriptedGenerator(CLEAN), judge)
    events = await ask(client)
    assert judge.inputs[0].reference_source is None
    assert done(events)["supported"] is True
    assert [slug for slug, _ in enqueue_calls] == ["pair-count"]
    await ask(client)  # second request: still no reference, but the queue dedupes by job id
    assert len(enqueue_calls) == 2


async def test_unsupported_problem_is_prompt_only_and_never_enqueued(
    client: AsyncClient, use, enqueue_calls: list
) -> None:
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    linked = {
        **PAIR_PROBLEM,
        "slug": "list-thing",
        "meta": {
            "name": "f",
            "params": [{"name": "head", "type": "ListNode"}],
            "return": {"type": "ListNode"},
        },
    }
    events = await ask(client, problem=linked)
    assert done(events)["supported"] is False and enqueue_calls == []
    assert shown(events) == CLEAN  # still guarded and served, prompt-only


async def seed_reference(factory: Any, status: str = "verified") -> None:
    async with factory() as session:
        session.add(
            Problem(
                slug="pair-count",
                title="Pair Count",
                difficulty="Easy",
                tags=[],
                meta=PAIR_PROBLEM["meta"],
                supported=True,
            )
        )
        await session.flush()
        session.add(
            ReferenceSolution(
                problem_slug="pair-count",
                module_source=GOOD_MODULE,
                comparison="exact",
                status=status,
                examples=[],
                verified_cases=300,
            )
        )
        await session.commit()


async def test_verified_reference_is_used_by_heuristics_and_judge(
    client: AsyncClient, use, db_session_factory, enqueue_calls: list
) -> None:
    await seed_reference(db_session_factory)
    judge = ScriptedJudge(NONE)
    use(ScriptedGenerator(LEAKY, CLEAN), judge)
    events = await ask(client, level=2)
    assert shown(events) == CLEAN  # the code-like draft was blocked by AST similarity
    assert judge.inputs[0].reference_source == GOOD_MODULE and enqueue_calls == []
    async with db_session_factory() as session:
        hint = (await session.scalars(select(Hint))).one()
        assert hint.guard_decision["first"]["stage"] == "heuristics"


async def test_failed_reference_is_prompt_only_and_not_rebuilt(
    client: AsyncClient, use, db_session_factory, enqueue_calls: list
) -> None:
    await seed_reference(db_session_factory, status="failed")
    judge = ScriptedJudge(NONE)
    use(ScriptedGenerator(CLEAN), judge)
    await ask(client)
    assert judge.inputs[0].reference_source is None and enqueue_calls == []


async def test_database_outage_degrades_to_a_prompt_only_hint(client: AsyncClient, use) -> None:
    from app.db import get_session_factory

    def broken() -> Any:
        raise ConnectionError("db down")

    app.dependency_overrides[get_session_factory] = lambda: broken
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    events = await ask(client)
    assert shown(events) == CLEAN and done(events)["supported"] is True


# ---- eval-only guard switch ----


@pytest.mark.parametrize("env", ["dev", "production", "test", ""])
async def test_disable_guard_header_is_ignored_outside_eval(
    client: AsyncClient, use, monkeypatch: pytest.MonkeyPatch, env: str
) -> None:
    monkeypatch.setenv("APORIA_ENV", env)
    reset_settings()
    use(ScriptedGenerator("a raw model reply"), ScriptedJudge(LEAK))
    headers = {**HEADERS, "X-Aporia-Disable-Guard": "1"}
    events = await ask(client, headers=headers)
    assert shown(events) == safe_hint("pair-count", 1)  # the guard still ran


async def test_disable_guard_header_is_honoured_in_eval(
    client: AsyncClient, use, monkeypatch: pytest.MonkeyPatch, db_session_factory
) -> None:
    monkeypatch.setenv("APORIA_ENV", "eval")
    reset_settings()
    judge = ScriptedJudge(LEAK)
    use(ScriptedGenerator("a raw model reply"), judge)
    headers = {**HEADERS, "X-Aporia-Disable-Guard": "1"}
    events = await ask(client, headers=headers)
    assert shown(events) == "a raw model reply" and judge.inputs == []
    async with db_session_factory() as session:
        assert (await session.scalars(select(Hint))).one().guard_decision == {"guard": "disabled"}
    # without the header the guard is on, even in eval
    events = await ask(client)
    assert shown(events) == safe_hint("pair-count", 1)


# ---- rating ----


async def test_rating_requires_ownership_and_valid_value(
    client: AsyncClient, use, db_session_factory
) -> None:
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    hint_id = done(await ask(client))["hint_id"]
    url = f"/v1/hint/{hint_id}/rating"
    assert (
        await client.post(url, json={"rating": 1}, headers={"X-Aporia-Device": "intruder"})
    ).status_code == 404
    assert (await client.post(url, json={"rating": 9}, headers=HEADERS)).status_code == 422
    assert (await client.post(url, json={"rating": 1})).status_code == 400
    assert (await client.post(url, json={"rating": 1}, headers=HEADERS)).status_code == 204
    async with db_session_factory() as session:
        assert (await session.scalars(select(Hint))).one().rating == 1
    # the plural path used by the extension is the same endpoint
    plural = f"/v1/hints/{hint_id}/rating"
    assert (await client.post(plural, json={"rating": 5}, headers=HEADERS)).status_code == 204
    async with db_session_factory() as session:
        assert (await session.scalars(select(Hint))).one().rating == 5
