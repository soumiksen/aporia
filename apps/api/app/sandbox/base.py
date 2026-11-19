from dataclasses import dataclass
from typing import Protocol


class SandboxError(RuntimeError):
    """The sandbox itself failed (unreachable, internal error). Not a failure of the code run."""


@dataclass(frozen=True)
class RunResult:
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    time_ms: float


class SandboxRunner(Protocol):
    """All untrusted code runs through this. Never `exec` untrusted code in the API process."""

    async def run(
        self, source: str, stdin: str, time_limit_s: float, memory_mb: int
    ) -> RunResult: ...
