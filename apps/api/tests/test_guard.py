import pytest

from app.config import Settings
from app.guard.guard import GuardDecision, check, guard_enabled, guarded_reply
from app.guard.llm_judge import GuardVerdict, JudgeInput, build_judge_messages
from app.guard.safe_hints import safe_hint
from app.schemas.hint import ProblemContext
from tests.support.modules import GOOD_MODULE

PROBLEM = ProblemContext(
    slug="pair-count",
    title="Pair Count",
    difficulty="Easy",
    tags=["Array"],
    content_text="Count pairs.",
    meta=None,
)
CLEAN = "What does your code do when the list has only two elements?"
LEAKY_CODE = "```python\ndef f(a, t):\n    m = {}\n    c = 0\n    for v in a:\n        c += m.get(t - v, 0)\n        m[v] = m.get(v, 0) + 1\n    return c\n```"  # noqa: E501

NONE = GuardVerdict(leaks=False, severity="none", reason="fine")
LEAK = GuardVerdict(leaks=True, severity="full", reason="gives the algorithm")


class Judge:
    def __init__(self, *verdicts: GuardVerdict | Exception):
        self.verdicts = list(verdicts)
        self.inputs: list[JudgeInput] = []

    async def __call__(self, inp: JudgeInput) -> GuardVerdict:
        self.inputs.append(inp)
        item = self.verdicts[min(len(self.inputs) - 1, len(self.verdicts) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


class Generator:
    def __init__(self, *drafts: str | Exception):
        self.drafts = list(drafts)
        self.feedback: list[str | None] = []

    async def __call__(self, feedback: str | None) -> str:
        self.feedback.append(feedback)
        item = self.drafts[min(len(self.feedback) - 1, len(self.drafts) - 1)]
        if isinstance(item, Exception):
            raise item
        return item


async def run(generator: Generator, judge: Judge, ref: str | None = None, level: int = 2):
    async def check_draft(draft: str) -> GuardDecision:
        return await check(draft, level, PROBLEM, ref, judge)

    return await guarded_reply(generator, check_draft, slug="pair-count", level=level)


# ---- check(): heuristics first, then the judge ----


async def test_heuristic_block_skips_the_judge() -> None:
    judge = Judge(NONE)
    decision = await check(LEAKY_CODE, 2, PROBLEM, GOOD_MODULE, judge)
    assert decision.leaks and decision.stage == "heuristics" and not judge.inputs


async def test_clean_draft_goes_to_the_judge_with_the_reference() -> None:
    judge = Judge(NONE)
    decision = await check(CLEAN, 2, PROBLEM, GOOD_MODULE, judge)
    assert not decision.leaks and decision.stage == "judge" and decision.judge_used
    assert judge.inputs[0].reference_source == GOOD_MODULE and judge.inputs[0].level == 2


async def test_without_reference_the_judge_gets_statement_only() -> None:
    judge = Judge(NONE)
    await check(CLEAN, 2, PROBLEM, None, judge)
    assert judge.inputs[0].reference_source is None
    prompt = build_judge_messages(judge.inputs[0])[1]["content"]
    assert "no verified reference" in prompt and "Count pairs." in prompt


async def test_partial_severity_counts_as_a_leak_even_if_flag_is_false() -> None:
    verdict = GuardVerdict(leaks=False, severity="partial", reason="reveals the key step")
    assert (await check(CLEAN, 2, PROBLEM, None, Judge(verdict))).leaks


# ---- policy ----


async def test_policy_pass() -> None:
    gen, judge = Generator(CLEAN), Judge(NONE)
    result = await run(gen, judge)
    assert result.text == CLEAN and result.rewrite_count == 0 and not result.used_safe_hint
    assert gen.feedback == [None]


async def test_policy_rewrite_then_pass_feeds_the_violation_back() -> None:
    gen, judge = Generator("Use a hash map of counts.", CLEAN), Judge(LEAK, NONE)
    result = await run(gen, judge)
    assert result.text == CLEAN and result.rewrite_count == 1 and not result.used_safe_hint
    assert gen.feedback[0] is None and "gives the algorithm" in (gen.feedback[1] or "")
    assert result.decision["first"]["leaks"] is True


async def test_policy_double_fail_returns_the_safe_hint() -> None:
    gen, judge = Generator("leak one", "leak two"), Judge(LEAK, LEAK)
    result = await run(gen, judge, level=3)
    assert result.used_safe_hint and result.text == safe_hint("pair-count", 3)
    assert result.rewrite_count == 1 and len(gen.feedback) == 2
    assert result.text not in ("leak one", "leak two")


async def test_policy_judge_exception_returns_the_safe_hint() -> None:
    result = await run(Generator("anything"), Judge(RuntimeError("judge down")))
    assert result.used_safe_hint and result.text == safe_hint("pair-count", 2)
    assert result.decision["error"] == "RuntimeError" and result.rewrite_count == 0


async def test_policy_judge_exception_on_the_rewrite_returns_the_safe_hint() -> None:
    result = await run(Generator("leak", CLEAN), Judge(LEAK, RuntimeError("down")))
    assert result.used_safe_hint and result.rewrite_count == 1 and result.text != CLEAN


async def test_policy_generation_failure_first_propagates_but_on_rewrite_fails_safe() -> None:
    with pytest.raises(RuntimeError, match="llm down"):
        await run(Generator(RuntimeError("llm down")), Judge(NONE))
    result = await run(Generator("leak", RuntimeError("llm down")), Judge(LEAK))
    assert result.used_safe_hint and result.rewrite_count == 1


async def test_a_heuristic_leak_never_reaches_the_client_unchecked() -> None:
    result = await run(Generator(LEAKY_CODE, LEAKY_CODE), Judge(NONE), ref=GOOD_MODULE)
    assert result.used_safe_hint and "def f" not in result.text


# ---- eval-only switch ----


@pytest.mark.parametrize(
    ("env", "header", "enabled"),
    [
        ("eval", "1", False),
        ("eval", None, True),
        ("eval", "0", True),
        ("dev", "1", True),
        ("production", "1", True),
        ("", "1", True),
    ],
)
def test_guard_can_only_be_disabled_in_eval(env: str, header: str | None, enabled: bool) -> None:
    settings = Settings(_env_file=None, aporia_env=env)  # type: ignore[call-arg]
    assert guard_enabled(settings, header) is enabled
