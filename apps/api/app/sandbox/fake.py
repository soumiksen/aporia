from collections.abc import Callable
from dataclasses import dataclass

from app.sandbox.base import RunResult

Scripted = RunResult | Callable[[str, str], RunResult] | Exception


@dataclass
class RunCall:
    source: str
    stdin: str
    time_limit_s: float
    memory_mb: int


class FakeRunner:
    """Runs nothing. Returns scripted results in order (the last one repeats) or from a callable."""

    def __init__(self, script: list[Scripted] | Callable[[str, str], RunResult] | None = None):
        self._script = script if script is not None else []
        self._index = 0
        self.calls: list[RunCall] = []

    async def run(
        self, source: str, stdin: str, time_limit_s: float = 5.0, memory_mb: int = 256
    ) -> RunResult:
        self.calls.append(RunCall(source, stdin, time_limit_s, memory_mb))
        if callable(self._script):
            return self._script(source, stdin)
        if not self._script:
            return RunResult(stdout="[]\n", stderr="", exit_code=0, timed_out=False, time_ms=1.0)
        item = self._script[min(self._index, len(self._script) - 1)]
        self._index += 1
        if isinstance(item, Exception):
            raise item
        if callable(item):
            return item(source, stdin)
        return item
