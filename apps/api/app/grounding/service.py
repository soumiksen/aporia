"""Execution grounding: find a failing input, shrink it, and build the hint context.

Total wall-clock budget 12 s. Any failure (timeout, sandbox error, unexpected error) degrades to
prompt-only hints; it never fails the request.
"""

import asyncio
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.grounding.context import GroundingContext, GuardFacts, build_context
from app.grounding.finder import (
    PER_CASE_TIMEOUT_S,
    Failure,
    ReferenceData,
    classify,
    find_failure,
    trace_summary,
)
from app.grounding.shrink import MAX_SECONDS, Budget, shrink
from app.sandbox.base import SandboxError, SandboxRunner
from app.sandbox.batch import run_cases

logger = logging.getLogger("aporia.grounding")

TOTAL_BUDGET_S = 12.0
SHRINK_MARGIN_S = 1.0  # stop shrinking this long before the hard cap


@dataclass
class GroundingResult:
    attempted: bool
    context: GroundingContext | None = None
    facts: GuardFacts | None = None
    failure: Failure | None = None
    error: str | None = None
    elapsed_ms: int = 0

    @property
    def grounded(self) -> bool:
        """True only when a real failing case was found and is used by the hint."""
        return self.failure is not None


def _key(args: Any) -> str:
    return json.dumps(args, sort_keys=True)


async def _shrink_failure(
    failure: Failure,
    problem: dict[str, Any],
    code: str,
    reference: ReferenceData,
    runner: SandboxRunner,
    deadline: float,
    clock: Callable[[], float],
) -> Failure:
    method = str((problem.get("meta") or {}).get("name", ""))
    observed: dict[str, tuple[Any, Any, str | None]] = {
        _key(failure.input): (failure.expected, failure.actual, failure.trace_summary)
    }

    async def still_fails(batch: list[Any]) -> list[bool]:
        ref_results, student_results = await asyncio.gather(
            run_cases(runner, reference.module_source, "reference", "", batch),
            run_cases(
                runner, code, "student", method, batch, PER_CASE_TIMEOUT_S, time_limit_s=30.0
            ),
        )
        flags = []
        for args, ref, stu in zip(batch, ref_results, student_results, strict=True):
            if not ref.ok:
                flags.append(False)
                continue
            kind = classify(stu, ref.out, reference.comparison)
            fails = kind == failure.kind  # same kind: do not morph a wrong answer into a crash
            if fails:
                observed[_key(args)] = (ref.out, stu.out, trace_summary(stu.err))
            flags.append(fails)
        return flags

    async def validate_batch(batch: list[Any]) -> list[bool]:
        results = await run_cases(runner, reference.module_source, "validate", "", batch)
        return [r.ok and r.out is True for r in results]

    budget = Budget(
        max_seconds=max(0.5, min(MAX_SECONDS, deadline - clock() - SHRINK_MARGIN_S)),
        clock=clock,
    )
    result = await shrink(
        failure.input, still_fails, lambda _: True, budget, validate_batch=validate_batch
    )
    expected, actual, trace = observed.get(
        _key(result.input), (failure.expected, failure.actual, failure.trace_summary)
    )
    return Failure(result.input, expected, actual, failure.kind, trace)


async def ground(
    problem: dict[str, Any],
    code: str,
    language: str,
    reference: ReferenceData | None,
    runner: SandboxRunner,
    *,
    total_budget_s: float = TOTAL_BUDGET_S,
    clock: Callable[[], float] = time.monotonic,
) -> GroundingResult:
    """Runs grounding if it can apply (Python code, supported problem, verified reference)."""
    if reference is None or not language.lower().startswith("python"):
        return GroundingResult(attempted=False)
    if not (problem.get("meta") or {}).get("name"):
        return GroundingResult(attempted=False)

    started = clock()
    deadline = started + total_budget_s

    async def run() -> GroundingResult:
        failure = await find_failure(
            problem, code, reference, runner, deadline=deadline, clock=clock
        )
        if failure is not None:
            failure = await _shrink_failure(
                failure, problem, code, reference, runner, deadline, clock
            )
        context, facts = build_context(failure)
        return GroundingResult(True, context, facts, failure)

    try:
        result = await asyncio.wait_for(run(), timeout=total_budget_s)
    except TimeoutError:
        result = GroundingResult(True, error="timeout")
    except SandboxError as exc:
        logger.warning("grounding: sandbox error: %s", exc)
        result = GroundingResult(True, error="sandbox_error")
    except Exception as exc:  # noqa: BLE001 - grounding must never fail the request
        logger.error("grounding failed: %s", type(exc).__name__)
        result = GroundingResult(True, error=f"error:{type(exc).__name__}")
    result.elapsed_ms = int((clock() - started) * 1000)
    return result
