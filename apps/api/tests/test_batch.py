import asyncio
import json

import pytest

from app.sandbox.base import RunResult, SandboxError
from app.sandbox.batch import run_cases
from app.sandbox.fake import FakeRunner
from tests.support.subprocess_runner import SubprocessRunner


def ok(stdout: str, **kw: object) -> RunResult:
    base = dict(stderr="", exit_code=0, timed_out=False, time_ms=1.0)
    base.update(kw)
    return RunResult(stdout=stdout, **base)  # type: ignore[arg-type]


def echo_results(stdin: str) -> list[dict]:
    cases = json.loads(stdin)["cases"]
    return [{"ok": True, "out": c[0], "err": None, "ms": 0.1} for c in cases]


async def test_cases_are_chunked_into_groups_of_50_and_order_is_preserved() -> None:
    def respond(source: str, stdin: str) -> RunResult:
        return ok(json.dumps(echo_results(stdin)))

    fake = FakeRunner(respond)
    cases = [[i] for i in range(120)]
    out = await run_cases(fake, "src", "reference", "", cases)
    assert [r.out for r in out] == list(range(120))
    sizes = sorted(len(json.loads(c.stdin)["cases"]) for c in fake.calls)
    assert sizes == [20, 50, 50]


async def test_order_survives_out_of_order_completion() -> None:
    delays = {0: 0.06, 1: 0.0, 2: 0.03}

    class Slow(FakeRunner):
        async def run(self, source, stdin, time_limit_s=5.0, memory_mb=256):  # type: ignore[override]
            first = json.loads(stdin)["cases"][0][0]
            await asyncio.sleep(delays[first // 50])
            return ok(json.dumps(echo_results(stdin)))

    out = await run_cases(Slow(), "src", "reference", "", [[i] for i in range(150)])
    assert [r.out for r in out] == list(range(150))


async def test_at_most_four_chunks_run_concurrently() -> None:
    in_flight = 0
    peak = 0

    class Counting(FakeRunner):
        async def run(self, source, stdin, time_limit_s=5.0, memory_mb=256):  # type: ignore[override]
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.02)
            in_flight -= 1
            return ok(json.dumps(echo_results(stdin)))

    await run_cases(Counting(), "src", "reference", "", [[i] for i in range(50 * 10)])
    assert peak == 4
    peak = 0
    await run_cases(Counting(), "src", "reference", "", [[i] for i in range(500)], concurrency=2)
    assert peak == 2


async def test_a_timed_out_chunk_only_fails_its_own_cases() -> None:
    def respond(source: str, stdin: str) -> RunResult:
        cases = json.loads(stdin)["cases"]
        if cases[0][0] == 50:  # the second chunk times out
            return ok("", timed_out=True, exit_code=-1)
        return ok(json.dumps(echo_results(stdin)))

    out = await run_cases(FakeRunner(respond), "src", "reference", "", [[i] for i in range(150)])
    assert [r.ok for r in out[:50]] == [True] * 50
    assert [r.ok for r in out[50:100]] == [False] * 50
    assert "time limit" in (out[50].err or "")
    assert [r.ok for r in out[100:]] == [True] * 50


async def test_empty_input_and_sandbox_errors() -> None:
    assert await run_cases(FakeRunner(), "src", "reference", "", []) == []
    with pytest.raises(SandboxError):
        await run_cases(FakeRunner([SandboxError("down")]), "src", "reference", "", [[1]])


async def test_real_harness_per_case_timeouts_across_chunks() -> None:
    src = "def solve_optimal(n):\n    while n > 0:\n        pass\n    return n\n"
    cases = [[0] if i % 60 else [1] for i in range(120)]  # 1 hangs, 0 returns immediately
    out = await run_cases(
        SubprocessRunner(), src, "reference", "", cases, per_case_timeout_s=0.2, time_limit_s=30
    )
    assert [r.ok for r in out] == [
        i % 60 != 0 for i in range(120)
    ]  # the two hanging cases fail alone
