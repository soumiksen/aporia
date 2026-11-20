import json
from collections.abc import Callable
from typing import Any

from app.grounding.finder import (
    Failure,
    ReferenceData,
    classify,
    find_failure,
    input_size,
    trace_summary,
)
from app.sandbox.base import RunResult
from app.sandbox.fake import FakeRunner
from app.sandbox.harness import CaseResult
from tests.support.modules import GOOD_MODULE, PAIR_PROBLEM
from tests.support.subprocess_runner import SubprocessRunner

# ---- a simulated sandbox: answers by mode without executing anything ----

Student = Callable[[list[Any]], Any]


def simulated(
    student: Student,
    reference: Callable[[list[Any]], Any],
    gen_inputs: dict[str, list[list[Any]]],
) -> FakeRunner:
    """Reference/student/gen modes answered by Python callables. `student` may raise."""

    def respond(source: str, stdin: str) -> RunResult:
        req = json.loads(stdin)
        if req["mode"] == "gen":
            items = []
            for size, count in req["sizes"].items():
                for args in gen_inputs.get(size, [])[:count]:
                    items.append({"size": size, "args": args, "valid": True, "err": None})
            return RunResult(json.dumps(items), "", 0, False, 1.0)
        fn = student if req["mode"] == "student" else reference
        out = []
        for args in req["cases"]:
            try:
                out.append({"ok": True, "out": fn(args), "err": None, "ms": 0.1})
            except TimeoutError:
                out.append(
                    {"ok": False, "out": None, "err": "TimeoutError: case timed out", "ms": 2000}
                )
            except Exception as exc:  # noqa: BLE001
                out.append(
                    {"ok": False, "out": None, "err": f"{type(exc).__name__}: {exc}", "ms": 0.1}
                )
        return RunResult(json.dumps(out), "", 0, False, 1.0)

    return FakeRunner(respond)


def ref_sum(args: list[Any]) -> int:
    return sum(args[0]) + args[1]


REFERENCE = ReferenceData(
    module_source="ignored by the simulator",
    comparison="exact",
    cases=[([[1, 2], 3], 6), ([[5], 0], 5)],
)
PROBLEM = {"slug": "p", "meta": {"name": "f", "params": [], "return": {"type": "integer"}}}
TINY = [[[i], 0] for i in range(1, 8)]
LARGE = [[list(range(60)), 1] for _ in range(5)]


async def find(student: Student, gen: dict | None = None, ref: ReferenceData = REFERENCE):
    runner = simulated(student, ref_sum, gen or {"tiny": TINY, "large": LARGE})
    return await find_failure(PROBLEM, "class Solution: ...", ref, runner)


async def test_wrong_answer_returns_the_smallest_failing_input() -> None:
    def student(args: list[Any]) -> int:
        nums, k = args
        return sum(nums) + k if len(nums) < 3 else 0  # wrong from 3 elements up

    failure = await find(student, {"tiny": [[[1, 2, 3, 4], 0], [[1, 2, 3], 0], [[1], 0]]})
    assert failure is not None and failure.kind == "wrong_answer"
    assert failure.input == [[1, 2, 3], 0]  # smaller than [1,2,3,4]
    assert failure.expected == 6 and failure.actual == 0 and failure.trace_summary is None


async def test_runtime_error_has_a_one_line_trace_summary() -> None:
    def student(args: list[Any]) -> int:
        if len(args[0]) == 1:
            raise IndexError("list index out of range")
        return ref_sum(args)

    failure = await find(student)
    assert failure is not None and failure.kind == "runtime_error"
    assert failure.trace_summary == "IndexError: list index out of range"
    assert "\n" not in (failure.trace_summary or "") and failure.actual is None


async def test_timeouts_are_judged_on_large_cases_and_rank_below_wrong_answers() -> None:
    def slow_on_large(args: list[Any]) -> int:
        if len(args[0]) >= 50:
            raise TimeoutError
        return ref_sum(args)

    failure = await find(slow_on_large)
    assert failure is not None and failure.kind == "timeout"
    assert len(failure.input[0]) == 60

    def wrong_small_and_slow_large(args: list[Any]) -> int:
        if len(args[0]) >= 50:
            raise TimeoutError
        return -1

    failure = await find(wrong_small_and_slow_large)
    assert failure is not None and failure.kind == "wrong_answer"  # priority over timeouts


async def test_a_correct_solution_has_no_failure() -> None:
    assert await find(ref_sum) is None


async def test_unordered_comparison_is_honoured() -> None:
    ref = ReferenceData("x", "unordered", [([[1, 2], 0], [1, 2])])
    runner = simulated(lambda a: [2, 1], lambda a: [1, 2], {})
    assert await find_failure(PROBLEM, "s", ref, runner) is None
    exact = ReferenceData("x", "exact", [([[1, 2], 0], [1, 2])])
    runner = simulated(lambda a: [2, 1], lambda a: [1, 2], {})
    assert (await find_failure(PROBLEM, "s", exact, runner)) is not None


async def test_missing_method_name_means_no_grounding() -> None:
    runner = simulated(ref_sum, ref_sum, {})
    assert await find_failure({"slug": "p", "meta": None}, "s", REFERENCE, runner) is None


async def test_large_phase_is_skipped_when_a_wrong_answer_is_found() -> None:
    runner = simulated(lambda a: -1, ref_sum, {"tiny": TINY, "large": LARGE})
    failure = await find_failure(PROBLEM, "s", REFERENCE, runner)
    assert failure is not None and failure.kind == "wrong_answer"
    gen_calls = [c for c in runner.calls if json.loads(c.stdin)["mode"] == "gen"]
    assert len(gen_calls) == 1  # only the tiny/small generation ran


# ---- helpers ----


def test_helpers() -> None:
    assert trace_summary("Traceback (most recent call last):\n  File x\nValueError: bad") == (
        "ValueError: bad"
    )
    assert trace_summary(None) is None and trace_summary("  \n ") is None
    assert len(trace_summary("E: " + "x" * 500) or "") == 200
    assert input_size([[1, 2], 3]) < input_size([[1, 2, 3, 4], 3])
    assert classify(CaseResult(True, 5, None, 0.1), 5, "exact") is None
    assert classify(CaseResult(True, 4, None, 0.1), 5, "exact") == "wrong_answer"
    assert classify(CaseResult(False, None, "X: y", 0.1), 5, "exact") == "runtime_error"
    assert (
        classify(CaseResult(False, None, "TimeoutError: case timed out", 0), 5, "exact")
        == "timeout"
    )
    assert Failure([1], 2, 3, "wrong_answer", None).kind == "wrong_answer"


# ---- end to end with real execution (trusted synthetic code) ----

BUGGY_STUDENT = """
class Solution:
    def pairCount(self, nums, target):
        count = 0
        for i in range(len(nums)):
            for j in range(i + 1, len(nums)):
                if nums[i] + nums[j] == target:
                    count += 1
                    break          # bug: stops after the first partner
        return count
"""

CORRECT_STUDENT = """
class Solution:
    def pairCount(self, nums, target):
        seen, count = {}, 0
        for x in nums:
            count += seen.get(target - x, 0)
            seen[x] = seen.get(x, 0) + 1
        return count
"""


async def test_real_execution_buggy_student_gets_a_failing_input() -> None:
    reference = ReferenceData(GOOD_MODULE, "exact", [([[1, 2, 3, 4], 5], 2)])
    failure = await find_failure(PAIR_PROBLEM, BUGGY_STUDENT, reference, SubprocessRunner())
    assert failure is not None and failure.kind == "wrong_answer"
    assert failure.expected != failure.actual
    # the failing input really fails: reproduce it with the two implementations
    ns: dict[str, Any] = {}
    exec(GOOD_MODULE, ns)  # noqa: S102 - trusted synthetic module
    assert ns["solve_optimal"](*failure.input) == failure.expected


async def test_real_execution_correct_student_has_no_failure() -> None:
    reference = ReferenceData(GOOD_MODULE, "exact", [([[1, 2, 3, 4], 5], 2)])
    assert await find_failure(PAIR_PROBLEM, CORRECT_STUDENT, reference, SubprocessRunner()) is None


async def test_real_execution_syntax_error_is_a_runtime_error() -> None:
    reference = ReferenceData(GOOD_MODULE, "exact", [([[1, 2, 3, 4], 5], 2)])
    failure = await find_failure(PAIR_PROBLEM, "class Solution(:\n", reference, SubprocessRunner())
    assert failure is not None and failure.kind == "runtime_error"
    assert "load failed" in (failure.trace_summary or "")
