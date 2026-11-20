import hashlib
import json
import re
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.hint import get_generator
from app.config import reset_settings
from app.grounding.context import GroundingContext, build_context, render_for_prompt
from app.grounding.finder import Failure, ReferenceData
from app.grounding.service import ground
from app.guard.heuristics import reveals_expected_output
from app.guard.llm_judge import get_judge
from app.guard.safe_hints import safe_hint
from app.main import app
from app.models import Attempt, Hint, Problem, ReferenceSolution, TestCase
from app.sandbox.base import SandboxError
from app.sandbox.fake import FakeRunner
from app.sandbox.provider import get_runner
from tests.support.modules import GOOD_MODULE, PAIR_PROBLEM
from tests.support.subprocess_runner import SubprocessRunner
from tests.test_finder import BUGGY_STUDENT, CORRECT_STUDENT
from tests.test_hint_ladder_guard import (
    CLEAN,
    NONE,
    ScriptedGenerator,
    ScriptedJudge,
    ask,
    done,
    shown,
)

# The documented fixture: a deliberately buggy student solution and the minimal failing input the
# pipeline must find. The bug (`break`) counts at most one partner per element, so the smallest
# failing input has exactly three elements.
MINIMAL_LENGTH = 3


def expected_for(args: list[Any]) -> Any:
    ns: dict[str, Any] = {}
    exec(GOOD_MODULE, ns)  # noqa: S102 - trusted synthetic module
    return ns["solve_optimal"](*args)


def buggy_for(args: list[Any]) -> Any:
    ns: dict[str, Any] = {}
    exec(BUGGY_STUDENT, ns)  # noqa: S102 - trusted synthetic code
    return ns["Solution"]().pairCount(*args)


async def seed(factory: Any) -> None:
    async with factory() as session:
        session.add(
            Problem(
                slug="pair-count", title="Pair Count", difficulty="Easy", tags=[],
                meta=PAIR_PROBLEM["meta"], supported=True,
            )
        )  # fmt: skip
        await session.flush()
        session.add(
            ReferenceSolution(
                problem_slug="pair-count", module_source=GOOD_MODULE, comparison="exact",
                status="verified", examples=[], verified_cases=300,
            )
        )  # fmt: skip
        session.add(
            TestCase(
                problem_slug="pair-count", args=[[1, 2, 3, 4], 5], expected=2, source="example"
            )
        )
        await session.commit()


@pytest.fixture
def sandbox():
    def install(runner: Any) -> None:
        app.dependency_overrides[get_runner] = lambda: runner

    yield install
    app.dependency_overrides.pop(get_runner, None)


@pytest.fixture
def use():
    def install(generator: Any, judge: Any) -> None:
        app.dependency_overrides[get_generator] = lambda: generator
        app.dependency_overrides[get_judge] = lambda: judge

    yield install
    app.dependency_overrides.pop(get_generator, None)
    app.dependency_overrides.pop(get_judge, None)


def failing_input_in(prompt: str) -> list[Any]:
    match = re.search(r"fails: (.+)", prompt)
    assert match, prompt
    return json.loads(match.group(1))


def user_prompt(gen: ScriptedGenerator, call: int = 0) -> str:
    return gen.calls[call][1]["content"]


async def test_grounded_hint_cites_a_minimal_failing_input_but_never_the_expected_output(
    client: AsyncClient, use, sandbox, db_session_factory
) -> None:
    await seed(db_session_factory)
    sandbox(SubprocessRunner())
    gen = ScriptedGenerator(CLEAN)
    judge = ScriptedJudge(NONE)
    use(gen, judge)

    events = await ask(client, level=1, code=BUGGY_STUDENT)  # first hint (any level grounds)
    assert done(events)["grounded"] is True and done(events)["failure_kind"] == "wrong_answer"
    events = await ask(client, level=2, code=BUGGY_STUDENT)
    info = done(events)
    assert (
        info["grounded"] is True and info["failure_kind"] == "wrong_answer" and info["level"] == 2
    )

    prompt = user_prompt(gen, 1)
    minimal = failing_input_in(prompt)
    assert len(minimal[0]) == MINIMAL_LENGTH  # minimal: two elements cannot expose the bug
    assert buggy_for(minimal) != expected_for(minimal)  # and it really fails
    assert "Do NOT state what the correct or expected output is" in prompt
    expected = expected_for(minimal)
    assert not reveals_expected_output(prompt.split("Grounding")[1], expected, buggy_for(minimal))
    assert "solve_optimal" not in prompt and "seen.get" not in prompt  # reference code never leaks
    assert f"returned: {buggy_for(minimal)}" in prompt  # the student's actual output is shown

    # the guard (and only the guard) received the expected output
    assert judge.inputs[-1].failing_case is not None
    assert judge.inputs[-1].failing_case["expected"] == expected
    assert judge.inputs[-1].reference_source == GOOD_MODULE


async def test_level_1_prompt_reveals_nothing_specific_but_the_hint_is_still_grounded(
    client: AsyncClient, use, sandbox
) -> None:
    sandbox(SubprocessRunner())
    use(gen := ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    # no verified reference yet: prompt-only
    events = await ask(client, level=1, code=BUGGY_STUDENT)
    assert done(events)["grounded"] is False
    assert "Grounding" not in user_prompt(gen)


async def test_level_1_with_a_reference_is_grounded_but_the_prompt_stays_generic(
    client: AsyncClient, use, sandbox, db_session_factory
) -> None:
    await seed(db_session_factory)
    sandbox(SubprocessRunner())
    use(gen := ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    events = await ask(client, level=1, code=BUGGY_STUDENT)
    assert done(events)["grounded"] is True
    assert "Grounding" not in user_prompt(gen) and "fails:" not in user_prompt(gen)


async def test_no_failing_input_found_never_claims_the_code_is_correct(
    client: AsyncClient, use, sandbox, db_session_factory
) -> None:
    await seed(db_session_factory)
    sandbox(SubprocessRunner())
    use(gen := ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    await ask(client, level=1, code=CORRECT_STUDENT)
    events = await ask(client, level=2, code=CORRECT_STUDENT)
    info = done(events)
    assert info["grounded"] is False and info["failure_kind"] is None
    prompt = user_prompt(gen, 1)
    assert "no failing input was found" in prompt and "Do NOT claim or imply" in prompt
    async with db_session_factory() as session:
        attempts = (await session.scalars(select(Attempt))).all()
        assert all(a.failing_case is None for a in attempts)


async def test_grounding_timeout_falls_back_to_prompt_only(
    client: AsyncClient, use, sandbox, db_session_factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    class Hanging(FakeRunner):
        async def run(self, source, stdin, time_limit_s=5.0, memory_mb=256):  # type: ignore[override]
            await asyncio.sleep(10)
            raise AssertionError("unreachable")

    monkeypatch.setenv("GROUNDING_BUDGET_S", "0.3")
    reset_settings()
    await seed(db_session_factory)
    sandbox(Hanging())
    use(gen := ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    events = await ask(client, level=2, code=BUGGY_STUDENT)
    assert shown(events) == CLEAN  # still generated and guarded
    info = done(events)
    assert info["grounded"] is False and info["failure_kind"] is None
    assert "Grounding" not in user_prompt(gen)


async def test_sandbox_error_falls_back_to_a_guarded_prompt_only_hint(
    client: AsyncClient, use, sandbox, db_session_factory
) -> None:
    await seed(db_session_factory)
    sandbox(FakeRunner([SandboxError("judge0 down")]))
    use(gen := ScriptedGenerator("a raw model reply"), ScriptedJudge(RuntimeError("judge down")))
    events = await ask(client, level=2, code=BUGGY_STUDENT)
    assert done(events)["grounded"] is False
    assert shown(events) == safe_hint("pair-count", 1)  # guard error still fails safe
    assert gen.calls  # the model was called (prompt-only), never shown raw


async def test_non_python_code_is_never_executed(
    client: AsyncClient, use, sandbox, db_session_factory
) -> None:
    await seed(db_session_factory)
    runner = FakeRunner()
    sandbox(runner)
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    events = await ask(client, level=2, code="int main() {}", language="cpp")
    assert done(events)["grounded"] is False and runner.calls == []


async def test_guard_rejects_a_reply_that_states_the_expected_output(
    client: AsyncClient, use, sandbox, db_session_factory
) -> None:
    await seed(db_session_factory)
    sandbox(SubprocessRunner())

    class Revealing(ScriptedGenerator):
        async def __call__(self, messages, model_env, **kw):  # type: ignore[override]
            self.calls.append(messages)
            prompt = messages[1]["content"]
            if "rejected because" in prompt or "fails:" not in prompt:  # rewrite, or level 1
                return CLEAN
            args = failing_input_in(prompt)
            return f"On that input the correct answer is {expected_for(args)}, so fix your loop."

    gen = Revealing(CLEAN)
    judge = ScriptedJudge(NONE)  # the judge would have approved: only the heuristic can catch it
    use(gen, judge)
    await ask(client, level=1, code=BUGGY_STUDENT)
    events = await ask(client, level=2, code=BUGGY_STUDENT)
    assert shown(events) == CLEAN and len(gen.calls) == 3  # L1 call, L2 draft, L2 rewrite
    async with db_session_factory() as session:
        hint = (await session.scalars(select(Hint).order_by(Hint.created_at.desc()))).first()
        assert hint is not None and hint.rewrite_count == 1
        assert "reveals_expected_output" in hint.guard_decision["first"]["reasons"]

    # if it keeps revealing, the safe hint is served
    class AlwaysRevealing(Revealing):
        async def __call__(self, messages, model_env, **kw):  # type: ignore[override]
            self.calls.append(messages)
            return (
                f"The expected output is {expected_for(failing_input_in(messages[1]['content']))}."
            )

    use(AlwaysRevealing(CLEAN), judge)
    events = await ask(client, level=2, code=BUGGY_STUDENT)
    assert shown(events) == safe_hint("pair-count", 2)


async def test_attempt_row_stores_a_code_hash_and_the_failing_input_only(
    client: AsyncClient, use, sandbox, db_session_factory
) -> None:
    await seed(db_session_factory)
    sandbox(SubprocessRunner())
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    await ask(client, level=1, code=BUGGY_STUDENT, last_verdict="Wrong Answer")
    async with db_session_factory() as session:
        attempt = (await session.scalars(select(Attempt))).one()
        hint = (await session.scalars(select(Hint))).one()
    assert attempt.code_hash == hashlib.sha256(BUGGY_STUDENT.encode()).hexdigest()
    assert attempt.verdict == "Wrong Answer"
    assert attempt.failing_case["kind"] == "wrong_answer" and "input" in attempt.failing_case
    assert BUGGY_STUDENT.strip() not in json.dumps(attempt.failing_case)
    assert hint.grounded is True and hint.failure_kind == "wrong_answer"
    assert not any(isinstance(v, str) and "class Solution" in v for v in vars(attempt).values())


async def test_attempt_is_recorded_even_for_prompt_only_hints(
    client: AsyncClient, use, db_session_factory
) -> None:
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    await ask(client, level=1, code="x = 1")
    async with db_session_factory() as session:
        attempt = (await session.scalars(select(Attempt))).one()
    assert attempt.verdict == "unknown" and attempt.failing_case is None


# ---- ground() directly: the documented minimal-failing-input fixture ----


async def test_pipeline_returns_the_minimal_failing_input_for_the_buggy_solution() -> None:
    reference = ReferenceData(GOOD_MODULE, "exact", [([[1, 2, 3, 4], 5], 2)])
    result = await ground(
        dict(PAIR_PROBLEM), BUGGY_STUDENT, "python3", reference, SubprocessRunner()
    )
    assert result.grounded and result.error is None and result.attempted
    failure = result.failure
    assert failure is not None and failure.kind == "wrong_answer"
    assert len(failure.input[0]) == MINIMAL_LENGTH
    assert failure.expected == expected_for(failure.input) != failure.actual
    assert result.facts is not None and result.facts.expected_output == failure.expected
    assert result.context is not None and not hasattr(result.context, "expected_output")


async def test_ground_degrades_instead_of_raising() -> None:
    reference = ReferenceData(GOOD_MODULE, "exact", [])
    problem = dict(PAIR_PROBLEM)
    down = await ground(
        problem, BUGGY_STUDENT, "python3", reference, FakeRunner([SandboxError("x")])
    )
    assert down.attempted and down.error == "sandbox_error" and not down.grounded
    none = await ground(problem, BUGGY_STUDENT, "python3", None, FakeRunner())
    assert not none.attempted and none.context is None
    nometa = await ground({"slug": "s", "meta": None}, "x", "python3", reference, FakeRunner())
    assert not nometa.attempted


# ---- context rendering and the expected-output check ----


def test_context_never_contains_the_expected_output() -> None:
    failure = Failure([[0, 0, 0], 0], expected=3, actual=2, kind="wrong_answer", trace_summary=None)
    context, facts = build_context(failure)
    assert facts is not None and facts.expected_output == 3
    for level in (1, 2, 3, 4):
        text = render_for_prompt(context, level)
        assert "expected" not in text.lower().replace(
            "do not state what the correct or expected", ""
        )
    l2 = render_for_prompt(context, 2)
    assert "[[0, 0, 0], 0]" in l2 and "returned: 2" in l2
    assert render_for_prompt(context, 1) == "" and render_for_prompt(None, 3) == ""


def test_context_renders_each_failure_kind() -> None:
    crash = build_context(Failure([[1]], None, None, "runtime_error", "IndexError: x"))[0]
    assert "raised an error: IndexError: x" in render_for_prompt(crash, 2)
    slow = build_context(Failure([[1] * 60], 1, None, "timeout", None))[0]
    assert "did not finish within the time limit" in render_for_prompt(slow, 3)
    none = GroundingContext("no_failure")
    text = render_for_prompt(none, 2)
    assert "no failing input was found" in text and "Do NOT claim" in text
    huge = build_context(Failure([["x" * 1000], 1, 2], 3, "y" * 1000, "wrong_answer", None))[0]
    assert len(render_for_prompt(huge, 2)) < 1200


@pytest.mark.parametrize(
    ("draft", "expected", "actual", "failing", "reveals"),
    [
        ("The expected output is 3.", 3, 2, [[1]], True),
        ("It should return [0, 1] here.", [0, 1], [], [[5]], True),
        ("The correct answer for this is true", True, False, [[1]], True),
        ('Expected: "abc"', "abc", "ab", ["x"], True),
        (
            "The result is [[1,2],[3,4]] when you run it correctly",
            [[1, 2], [3, 4]],
            [],
            [[9]],
            True,
        ),
        ("Your code returns 2 here. What should it return?", 3, 2, [[1]], False),
        ("Trace your code on [0, 0, 0] with k = 3.", 3, 2, [[0, 0, 0], 3], False),
        ("Look at nums = [1, 2] carefully", [[1, 2]], [], [[1, 2]], False),
        ("Count how many pairs you find: 3 is a lot", 7, 1, [[1]], False),
    ],
)
def test_reveals_expected_output(
    draft: str, expected: Any, actual: Any, failing: Any, reveals: bool
) -> None:
    assert reveals_expected_output(draft, expected, actual, failing) is reveals
