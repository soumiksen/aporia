import json
import os

import httpx
import pytest

from app.sandbox.base import RunResult, SandboxError
from app.sandbox.fake import FakeRunner
from app.sandbox.harness import build_program, run_cases, run_gen
from app.sandbox.judge0 import Judge0Runner, b64
from tests.support.subprocess_runner import SubprocessRunner

STUDENT = """
from typing import List

class Solution:
    def twoSum(self, nums: List[int], target: int) -> List[int]:
        seen = {}
        for i, x in enumerate(nums):
            if target - x in seen:
                return [seen[target - x], i]
            seen[x] = i
        return []
"""

MODULE = """
import random

def solve_optimal(nums, target):
    return sum(nums) + target

def solve_brute(nums, target):
    total = 0
    for x in nums:
        total += x
    return total + target

def gen(rng: random.Random, size: str) -> list:
    n = {"tiny": 2, "small": 5, "large": 50}[size]
    return [[rng.randint(-5, 5) for _ in range(n)], rng.randint(0, 3)]

def validate(args: list) -> bool:
    return len(args[0]) >= 2 and args[1] >= 1
"""


def ok_result(stdout: str, **kw: object) -> RunResult:
    base = dict(stderr="", exit_code=0, timed_out=False, time_ms=5.0)
    base.update(kw)
    return RunResult(stdout=stdout, **base)  # type: ignore[arg-type]


# ---- harness against a real subprocess (trusted synthetic code only) ----


async def test_student_mode_runs_cases() -> None:
    out = await run_cases(
        SubprocessRunner(),
        mode="student",
        source=STUDENT,
        method="twoSum",
        cases=[[[2, 7, 11, 15], 9], [[3, 2, 4], 6], [[1, 2], 99]],
    )
    assert [r.out for r in out] == [[0, 1], [1, 2], []]
    assert all(r.ok for r in out)


async def test_student_runtime_error_and_missing_method() -> None:
    bad = "class Solution:\n    def twoSum(self, nums, target):\n        return 1 // 0\n"
    out = await run_cases(
        SubprocessRunner(), mode="student", source=bad, method="twoSum", cases=[[[1], 1]]
    )
    assert not out[0].ok and "ZeroDivisionError" in (out[0].err or "")
    out = await run_cases(
        SubprocessRunner(), mode="student", source=bad, method="nope", cases=[[[1], 1]]
    )
    assert not out[0].ok and "no Solution.nope" in (out[0].err or "")


async def test_syntax_error_in_source_fails_each_case() -> None:
    out = await run_cases(
        SubprocessRunner(),
        mode="student",
        source="class Solution(:\n",
        method="x",
        cases=[[1], [2]],
    )
    assert [r.ok for r in out] == [False, False]
    assert "load failed" in (out[0].err or "")


async def test_per_case_timeout_does_not_stop_other_cases() -> None:
    slow = "def solve_optimal(n):\n    while n > 0:\n        pass\n    return n\n"
    out = await run_cases(
        SubprocessRunner(),
        mode="reference",
        source=slow,
        method="",
        cases=[[0], [1], [0]],
        per_case_timeout_s=0.3,
    )
    assert [r.ok for r in out] == [True, False, True]
    assert "timed out" in (out[1].err or "")


async def test_student_print_does_not_corrupt_output() -> None:
    noisy = "class Solution:\n    def f(self, x):\n        print('hello')\n        return x + 1\n"
    out = await run_cases(SubprocessRunner(), mode="student", source=noisy, method="f", cases=[[1]])
    assert out[0].ok and out[0].out == 2


async def test_cases_are_isolated_from_mutation() -> None:
    src = "def solve_optimal(xs):\n    xs.append(1)\n    return len(xs)\n"
    out = await run_cases(
        SubprocessRunner(), mode="reference", source=src, method="", cases=[[[0]], [[0]]]
    )
    assert [r.out for r in out] == [2, 2]


async def test_non_json_output_is_reported() -> None:
    src = "def solve_optimal(x):\n    return {1, 2}\n"
    out = await run_cases(SubprocessRunner(), mode="reference", source=src, method="", cases=[[1]])
    assert not out[0].ok and "JSON" in (out[0].err or "")


async def test_reference_modes_and_gen() -> None:
    runner = SubprocessRunner()
    opt = await run_cases(runner, mode="reference", source=MODULE, method="", cases=[[[1, 2], 3]])
    brute = await run_cases(
        runner, mode="reference_brute", source=MODULE, method="", cases=[[[1, 2], 3]]
    )
    assert opt[0].out == brute[0].out == 6
    cases = await run_gen(runner, source=MODULE, seed=7, sizes={"tiny": 4, "small": 4, "large": 2})
    assert len(cases) == 10 and {c.size for c in cases} == {"tiny", "small", "large"}
    again = await run_gen(runner, source=MODULE, seed=7, sizes={"tiny": 4, "small": 4, "large": 2})
    assert [c.args for c in cases] == [c.args for c in again]  # seeded and deterministic
    assert any(not c.valid for c in cases) or all(c.valid for c in cases)


# ---- batching and failure handling with the fake runner ----


async def test_cases_are_packed_into_batches_of_50() -> None:
    def respond(source: str, stdin: str) -> RunResult:
        n = len(json.loads(stdin)["cases"])
        payload = [{"ok": True, "out": 1, "err": None, "ms": 0.1}] * n
        return ok_result("noise\n" + json.dumps(payload) + "\n")

    fake = FakeRunner(respond)
    out = await run_cases(
        fake, mode="reference", source="x", method="", cases=[[i] for i in range(120)]
    )
    assert len(out) == 120 and len(fake.calls) == 3
    assert [len(json.loads(c.stdin)["cases"]) for c in fake.calls] == [50, 50, 20]


async def test_failed_batch_becomes_failed_cases_not_an_exception() -> None:
    fake = FakeRunner([ok_result("", timed_out=True, exit_code=-1)])
    out = await run_cases(fake, mode="reference", source="x", method="", cases=[[1], [2]])
    assert [r.ok for r in out] == [False, False]
    assert "time limit" in (out[0].err or "")


async def test_bad_json_and_count_mismatch() -> None:
    out = await run_cases(
        FakeRunner([ok_result("not json")]), mode="reference", source="x", method="", cases=[[1]]
    )
    assert not out[0].ok
    mismatch = ok_result(json.dumps([{"ok": True, "out": 1, "err": None, "ms": 0}]))
    out = await run_cases(
        FakeRunner([mismatch]), mode="reference", source="x", method="", cases=[[1], [2]]
    )
    assert [r.err for r in out] == ["sandbox: result count mismatch"] * 2


async def test_sandbox_infrastructure_error_propagates() -> None:
    with pytest.raises(SandboxError):
        await run_cases(
            FakeRunner([SandboxError("down")]), mode="reference", source="x", method="", cases=[[1]]
        )
    with pytest.raises(SandboxError):
        await run_gen(
            FakeRunner([ok_result("", exit_code=1)]), source="x", seed=1, sizes={"tiny": 1}
        )


def test_program_embeds_source_safely() -> None:
    program = build_program("x = '''\\n'''\nprint(\"hi\")", 1.5)
    compile(program, "<harness>", "exec")  # always valid Python, whatever the source contains
    assert "1.5" in program


# ---- Judge0 client against a mocked HTTP API (no network) ----


def judge0_transport(submission: dict, seen: list[httpx.Request]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path == "/languages":
            return httpx.Response(
                200,
                json=[
                    {"id": 63, "name": "JavaScript (Node.js 12.14.0)"},
                    {"id": 71, "name": "Python (3.8.1)"},
                    {"id": 70, "name": "Python (2.7.17)"},
                ],
            )
        return httpx.Response(200, json=submission)

    return httpx.MockTransport(handler)


async def test_judge0_resolves_language_and_maps_result() -> None:
    seen: list[httpx.Request] = []
    submission = {
        "stdout": b64("[1]\n"),
        "stderr": None,
        "exit_code": 0,
        "time": "0.012",
        "status": {"id": 3, "description": "Accepted"},
    }
    client = httpx.AsyncClient(transport=judge0_transport(submission, seen))
    runner = Judge0Runner("http://judge0", client)
    result = await runner.run("print(1)", "in", 2.0, 128)
    await runner.run("print(1)", "in", 2.0, 128)
    assert result.stdout == "[1]\n" and result.exit_code == 0 and not result.timed_out
    assert result.time_ms == pytest.approx(12.0)
    assert sum(r.url.path == "/languages" for r in seen) == 1  # resolved once
    post = next(r for r in seen if r.url.path == "/submissions")
    assert post.url.params["base64_encoded"] == "true" and post.url.params["wait"] == "true"
    body = json.loads(post.content)
    assert body["language_id"] == 71 and body["enable_network"] is False
    assert body["memory_limit"] == 128 * 1024 and body["cpu_time_limit"] == 2.0


async def test_judge0_timeout_and_internal_error() -> None:
    tle = {"stdout": None, "status": {"id": 5, "description": "Time Limit Exceeded"}, "time": "2.0"}
    runner = Judge0Runner("http://judge0", httpx.AsyncClient(transport=judge0_transport(tle, [])))
    assert (await runner.run("x", "", 1.0, 64)).timed_out is True
    internal = {"status": {"id": 13, "description": "Internal Error"}}
    runner = Judge0Runner(
        "http://judge0", httpx.AsyncClient(transport=judge0_transport(internal, []))
    )
    with pytest.raises(SandboxError, match="Internal Error"):
        await runner.run("x", "", 1.0, 64)


async def test_judge0_unreachable_is_a_sandbox_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    runner = Judge0Runner("http://judge0", httpx.AsyncClient(transport=httpx.MockTransport(boom)))
    with pytest.raises(SandboxError):
        await runner.run("x", "", 1.0, 64)


# ---- integration against a real Judge0 (skipped unless reachable) ----


def judge0_url() -> str:
    return os.environ.get("JUDGE0_URL", "http://localhost:2358")


async def judge0_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=1.0) as client:
            return (await client.get(f"{judge0_url()}/languages")).status_code == 200
    except httpx.HTTPError:
        return False


@pytest.mark.sandbox
async def test_judge0_integration_runs_trivial_program() -> None:
    if not await judge0_reachable():
        pytest.skip("Judge0 not reachable (set JUDGE0_URL and start the sandbox profile)")
    runner = Judge0Runner(judge0_url())
    try:
        result = await runner.run("print(1 + 1)", "", 5.0, 128)
    except SandboxError as exc:
        if "Internal Error" in str(exc):
            # Judge0 CE 1.13 needs cgroup v1; Docker Desktop (cgroup v2) cannot run submissions.
            pytest.skip(f"Judge0 is up but cannot execute on this host: {exc}")
        raise
    assert result.stdout.strip() == "2" and result.exit_code == 0
