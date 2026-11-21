"""Replaces `build_reference` with a scripted outcome per slug."""

from typing import Any

from app.reference.pipeline import ReferenceResult


def install(monkeypatch: Any, outcomes: dict[str, str]) -> None:
    async def fake_build(problem, *, llm, runner, seed=0):
        kind = outcomes[problem["slug"]]
        if kind == "verified":
            return ReferenceResult(
                "verified", None, "def solve_optimal(x):\n    return x\n", "exact",
                [{"args": [1], "expected": 1}], 300,
            )  # fmt: skip
        if kind == "infra":
            return ReferenceResult("failed", "llm down", infrastructure_error=True)
        return ReferenceResult("failed", "mismatch")

    monkeypatch.setattr("app.reference.pipeline.build_reference", fake_build)
