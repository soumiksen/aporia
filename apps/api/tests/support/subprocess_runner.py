"""Test-only runner: executes the harness in a local subprocess.

NOT a sandbox (no network or filesystem isolation). Only ever feed it trusted, synthetic code in
tests. It exists so the harness template and the reference pipeline can be tested for real
without Judge0 (which does not run on every host).
"""

import asyncio
import sys
import time

from app.sandbox.base import RunResult


class SubprocessRunner:
    async def run(
        self, source: str, stdin: str, time_limit_s: float = 5.0, memory_mb: int = 256
    ) -> RunResult:
        started = time.perf_counter()
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-c",
            source,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(stdin.encode()), time_limit_s)
            timed_out = False
        except TimeoutError:
            proc.kill()
            out, err = await proc.communicate()
            timed_out = True
        return RunResult(
            stdout=out.decode(errors="replace"),
            stderr=err.decode(errors="replace"),
            exit_code=proc.returncode if proc.returncode is not None else -1,
            timed_out=timed_out,
            time_ms=(time.perf_counter() - started) * 1000,
        )
