"""Finds a failing input for the student's code by running it against the verified reference."""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.reference.compare import outputs_equal
from app.sandbox.base import SandboxRunner
from app.sandbox.batch import run_cases
from app.sandbox.harness import CaseResult, run_gen

FailureKind = Literal["wrong_answer", "runtime_error", "timeout"]

FINDER_SEED = 4242  # distinct from the pipeline's seed so fresh cases differ from stored ones
STORED_CASE_CAP = 150
FRESH_SIZES = {"tiny": 60, "small": 40}  # 100 fresh cases
LARGE_SIZES = {"large": 20}
PER_CASE_TIMEOUT_S = 2.0
TRACE_CHARS = 200


@dataclass(frozen=True)
class ReferenceData:
    """What the finder needs from a verified reference (loaded from the database)."""

    module_source: str
    comparison: str = "exact"
    # (args, expected) pairs: statement examples first, then stored generated cases.
    cases: list[tuple[list[Any], Any]] = field(default_factory=list)


@dataclass(frozen=True)
class Failure:
    input: list[Any]
    expected: Any
    actual: Any
    kind: FailureKind
    trace_summary: str | None  # last line of the exception only, never a full traceback


def input_size(args: list[Any]) -> int:
    return len(json.dumps(args, separators=(",", ":")))


def trace_summary(err: str | None) -> str | None:
    """Last non-empty line of the error text, truncated."""
    if not err:
        return None
    lines = [line.strip() for line in err.strip().splitlines() if line.strip()]
    return lines[-1][:TRACE_CHARS] if lines else None


def classify(result: CaseResult, expected: Any, comparison: str) -> FailureKind | None:
    if not result.ok:
        return "timeout" if "timed out" in (result.err or "") else "runtime_error"
    if not outputs_equal(result.out, expected, comparison):
        return "wrong_answer"
    return None


def _dedupe(
    pairs: list[tuple[list[Any], Any]],
) -> list[tuple[list[Any], Any]]:
    seen: set[str] = set()
    out = []
    for args, expected in pairs:
        key = json.dumps(args, sort_keys=True)
        if key not in seen:
            seen.add(key)
            out.append((args, expected))
    return out


async def _fresh_cases(
    runner: SandboxRunner, reference: ReferenceData, sizes: dict[str, int], seed: int
) -> list[tuple[list[Any], Any]]:
    """Generated valid inputs with expected outputs computed by the reference."""
    generated = await run_gen(runner, source=reference.module_source, seed=seed, sizes=sizes)
    inputs = [g.args for g in generated if g.valid and g.args is not None]
    if not inputs:
        return []
    results = await run_cases(runner, reference.module_source, "reference", "", inputs)
    return [(a, r.out) for a, r in zip(inputs, results, strict=True) if r.ok]


async def _first_failures(
    runner: SandboxRunner,
    student_code: str,
    method: str,
    reference: ReferenceData,
    pairs: list[tuple[list[Any], Any]],
    *,
    chunk_size: int,
) -> list[Failure]:
    if not pairs:
        return []
    results = await run_cases(
        runner,
        student_code,
        "student",
        method,
        [args for args, _ in pairs],
        PER_CASE_TIMEOUT_S,
        chunk_size=chunk_size,
        time_limit_s=30.0,
    )
    failures = []
    for (args, expected), result in zip(pairs, results, strict=True):
        kind = classify(result, expected, reference.comparison)
        if kind:
            failures.append(Failure(args, expected, result.out, kind, trace_summary(result.err)))
    return failures


def _pick(failures: list[Failure]) -> Failure | None:
    """runtime_error and wrong_answer on the smallest input first; timeouts only after those."""
    if not failures:
        return None
    primary = [f for f in failures if f.kind != "timeout"]
    pool = primary or failures
    return min(pool, key=lambda f: input_size(f.input))


async def find_failure(
    problem: dict[str, Any],
    student_code: str,
    reference: ReferenceData,
    runner: SandboxRunner,
    *,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> Failure | None:
    """Returns a failing case (not yet shrunk), or None if none was found.

    Phase A: statement examples, stored test cases, 100 fresh tiny/small cases. Phase B (only if A
    found no wrong answer or runtime error): 20 large cases, where timeouts are judged.
    Raises SandboxError if the sandbox itself fails (the caller falls back to prompt-only).
    """
    method = str((problem.get("meta") or {}).get("name", ""))
    if not method:
        return None

    stored = reference.cases[:STORED_CASE_CAP]
    fresh = await _fresh_cases(runner, reference, FRESH_SIZES, FINDER_SEED)
    phase_a = _dedupe([*stored, *fresh])
    failures = await _first_failures(
        runner, student_code, method, reference, phase_a, chunk_size=50
    )
    picked = _pick(failures)
    if picked and picked.kind != "timeout":
        return picked
    if deadline is not None and clock() > deadline:
        return picked

    large = await _fresh_cases(runner, reference, LARGE_SIZES, FINDER_SEED + 1)
    large_failures = await _first_failures(
        runner, student_code, method, reference, large, chunk_size=10
    )
    return _pick([*failures, *large_failures])
