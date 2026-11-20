from app.config import get_settings
from app.sandbox.base import SandboxRunner
from app.sandbox.judge0 import Judge0Runner

_runner: SandboxRunner | None = None


def get_runner() -> SandboxRunner:
    """The production sandbox (Judge0), created once. Tests override this dependency."""
    global _runner
    if _runner is None:
        _runner = Judge0Runner(get_settings().judge0_url)
    return _runner
