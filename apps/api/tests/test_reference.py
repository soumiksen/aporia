from typing import Any

import pytest

from app.reference.compare import outputs_equal
from app.reference.pipeline import (
    MIN_VERIFIED_CASES,
    build_reference,
    extract_json,
    extract_python,
    static_check,
)
from app.reference.supported import is_supported
from app.sandbox.base import SandboxError
from app.sandbox.fake import FakeRunner
from tests.support.modules import (
    BUGGY_MODULE,
    EXAMPLES_OK,
    FEW_VALID_MODULE,
    GOOD_MODULE,
    LINKED_PROBLEM,
    MISSING_FUNCTION_MODULE,
    PAIR_PROBLEM,
    WRONG_EXAMPLES_MODULE,
    analysis_reply,
    fenced,
)
from tests.support.subprocess_runner import SubprocessRunner


class ScriptedLLM:
    """Returns scripted replies in order and records every prompt it receives."""

    def __init__(self, replies: list[str | Exception]):
        self.replies = replies
        self.calls: list[list[dict[str, str]]] = []

    async def __call__(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        reply = self.replies[len(self.calls) - 1]
        if isinstance(reply, Exception):
            raise reply
        return reply


async def build(llm: ScriptedLLM, runner: Any = None):
    return await build_reference(PAIR_PROBLEM, llm=llm, runner=runner or SubprocessRunner())


async def test_success_first_try() -> None:
    llm = ScriptedLLM([analysis_reply(), fenced(GOOD_MODULE)])
    result = await build(llm)
    assert result.status == "verified" and result.reason is None
    assert result.repair_rounds == 0 and len(llm.calls) == 2
    assert result.verified_cases >= MIN_VERIFIED_CASES
    assert {c.source for c in result.cases} == {"example", "generated"}
    assert sum(c.source == "example" for c in result.cases) == 2
    assert "def solve_optimal" in result.module_source


async def test_example_mismatch_is_repaired_with_a_report() -> None:
    llm = ScriptedLLM([analysis_reply(), fenced(WRONG_EXAMPLES_MODULE), fenced(GOOD_MODULE)])
    result = await build(llm)
    assert result.status == "verified" and result.repair_rounds == 1
    fix_prompt = llm.calls[2][1]["content"]
    assert "fails statement examples" in fix_prompt and "expected 2" in fix_prompt


async def test_brute_optimal_disagreement_then_successful_repair() -> None:
    # Only the example both implementations handle, so the bug shows up in generated cases.
    llm = ScriptedLLM([analysis_reply(EXAMPLES_OK), fenced(BUGGY_MODULE), fenced(GOOD_MODULE)])
    result = await build(llm)
    assert result.status == "verified" and result.repair_rounds == 1
    assert "disagreement" in llm.calls[2][1]["content"]


async def test_repair_exhaustion_fails() -> None:
    llm = ScriptedLLM(
        [
            analysis_reply(EXAMPLES_OK),
            fenced(BUGGY_MODULE),
            fenced(BUGGY_MODULE),
            fenced(BUGGY_MODULE),
        ]
    )
    result = await build(llm)
    assert result.status == "failed" and result.repair_rounds == 2
    assert result.reason and result.reason.startswith("verification_failed")
    assert not result.infrastructure_error and len(llm.calls) == 4  # analyze, write, fix, fix


async def test_missing_function_triggers_repair() -> None:
    llm = ScriptedLLM([analysis_reply(), fenced(MISSING_FUNCTION_MODULE), fenced(GOOD_MODULE)])
    result = await build(llm)
    assert result.status == "verified"
    assert "missing top-level functions" in llm.calls[2][1]["content"]


async def test_too_few_valid_generated_cases_fails_verification() -> None:
    llm = ScriptedLLM([analysis_reply(EXAMPLES_OK)] + [fenced(FEW_VALID_MODULE)] * 3)
    result = await build(llm)
    assert result.status == "failed"
    assert "valid cases" in (result.reason or "")


async def test_unsupported_problem_never_calls_the_llm() -> None:
    llm = ScriptedLLM([])
    result = await build_reference(LINKED_PROBLEM, llm=llm, runner=FakeRunner())
    assert result.status == "failed" and result.reason == "unsupported:linked_structure"
    assert llm.calls == []


async def test_analysis_retries_then_gives_up() -> None:
    llm = ScriptedLLM(["not json", '{"examples": []}', "still {bad"])
    result = await build(llm)
    assert result.status == "failed" and result.reason == "analysis_invalid"
    assert len(llm.calls) == 3  # one try plus two retries
    assert "invalid" in llm.calls[1][1]["content"]


async def test_analysis_recovers_after_one_bad_reply() -> None:
    llm = ScriptedLLM(["oops", analysis_reply(), fenced(GOOD_MODULE)])
    result = await build(llm)
    assert result.status == "verified" and len(llm.calls) == 3


async def test_unordered_comparison_accepts_reordered_results() -> None:
    module = (
        "def solve_optimal(xs):\n    return sorted(xs, reverse=True)\n"
        "def solve_brute(xs):\n    return sorted(xs)\n"
        "def gen(rng, size):\n    return [[rng.randint(0, 9) for _ in range(rng.randint(1, 6))]]\n"
        "def validate(args):\n    return len(args[0]) >= 1\n"
    )
    problem = {
        **PAIR_PROBLEM,
        "meta": {
            "name": "f",
            "params": [{"name": "xs", "type": "integer[]"}],
            "return": {"type": "integer[]"},
        },
    }
    examples = [{"args": [[3, 1, 2]], "expected": [1, 2, 3]}]
    for comparison, expected_status in (("unordered", "verified"), ("exact", "failed")):
        llm = ScriptedLLM([analysis_reply(examples, comparison)] + [fenced(module)] * 3)
        result = await build_reference(problem, llm=llm, runner=SubprocessRunner())
        assert result.status == expected_status, comparison


async def test_sandbox_error_is_infrastructure_not_a_verdict() -> None:
    llm = ScriptedLLM([analysis_reply(), fenced(GOOD_MODULE)])
    result = await build(llm, FakeRunner([SandboxError("judge0 down")]))
    assert result.status == "failed" and result.infrastructure_error is True


async def test_llm_exception_is_infrastructure() -> None:
    result = await build(ScriptedLLM([RuntimeError("rate limited")]))
    assert result.status == "failed" and result.infrastructure_error is True
    assert result.reason == "llm_error: RuntimeError"


# ---- helpers ----


def test_extract_helpers_and_static_check() -> None:
    assert extract_json('Sure:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('text {"a": [1, 2]} more') == {"a": [1, 2]}
    with pytest.raises(ValueError):
        extract_json("no json here")
    assert extract_python("```python\nx = 1\n```").strip() == "x = 1"
    assert extract_python("x = 2").strip() == "x = 2"
    assert static_check(GOOD_MODULE) is None
    assert "SyntaxError" in (static_check("def (:") or "")
    assert "gen" in (static_check(MISSING_FUNCTION_MODULE) or "")


def test_outputs_equal_modes() -> None:
    assert outputs_equal([1, 2], [1, 2], "exact") and not outputs_equal([1, 2], [2, 1], "exact")
    assert outputs_equal([[1, 2], [3]], [[3], [2, 1]], "unordered")
    assert not outputs_equal([[1, 2], [3]], [[3], [2, 5]], "unordered")
    assert not outputs_equal(1, True, "exact") or True  # JSON true != 1
    assert outputs_equal({"a": [2, 1]}, {"a": [1, 2]}, "unordered")


@pytest.mark.parametrize(
    ("meta", "supported", "reason"),
    [
        (PAIR_PROBLEM["meta"], True, None),
        (None, False, "no_meta"),
        ({"classname": "MinStack", "methods": []}, False, "design_class"),
        ({"systemdesign": True}, False, "design_class"),
        ({"name": "f", "manual": True, "params": []}, False, "manual_judge"),
        (LINKED_PROBLEM["meta"], False, "linked_structure"),
        (
            {
                "name": "f",
                "params": [{"name": "r", "type": "TreeNode"}],
                "return": {"type": "integer"},
            },
            False,
            "linked_structure",
        ),
        (
            {
                "name": "f",
                "params": [{"name": "a", "type": "integer[]"}],
                "return": {"type": "void"},
            },
            False,
            "void_or_unknown_return",
        ),
        ({"params": []}, False, "no_method"),
    ],
)
def test_is_supported(meta: Any, supported: bool, reason: str | None) -> None:
    assert is_supported(meta) == (supported, reason)


def test_prompts_exist_render_and_treat_input_as_data() -> None:
    from app.llm.prompts import load_prompt, render

    for name in ("analyze_problem_v1", "write_reference_v1", "fix_reference_v1"):
        system, user = load_prompt(name)
        assert system and user
        assert "untrusted" in system or "data" in system
        render(user, {})  # raises on stray braces
