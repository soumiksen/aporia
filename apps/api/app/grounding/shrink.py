"""Generic delta-debugging shrinker for JSON argument lists.

Pure and sandbox-agnostic: `still_fails` (batch predicate) and `validate` are injected.
Given a failing input it greedily replaces it with smaller candidates that still fail, until no
candidate fails (a local minimum), or the budget runs out (then the best input so far is returned).
"""

import json
import time
from collections.abc import Awaitable, Callable, Iterator
from dataclasses import dataclass, field
from itertools import zip_longest
from typing import Any

MAX_EVALUATIONS = 150
MAX_SECONDS = 15.0
MAX_BATCH = 8  # candidates evaluated in parallel per round (small: keeps the 150-run budget useful)

StillFails = Callable[[list[Any]], Awaitable[list[bool]]]
Validate = Callable[[Any], bool]
ValidateBatch = Callable[[list[Any]], Awaitable[list[bool]]]


@dataclass
class Budget:
    max_evaluations: int = MAX_EVALUATIONS
    max_seconds: float = MAX_SECONDS
    clock: Callable[[], float] = time.monotonic
    evaluations: int = 0
    _started: float | None = field(default=None, repr=False)

    def start(self) -> None:
        if self._started is None:
            self._started = self.clock()

    @property
    def remaining_evaluations(self) -> int:
        return max(0, self.max_evaluations - self.evaluations)

    @property
    def out_of_time(self) -> bool:
        return self._started is not None and self.clock() - self._started >= self.max_seconds

    @property
    def exhausted(self) -> bool:
        return self.remaining_evaluations == 0 or self.out_of_time


@dataclass(frozen=True)
class ShrinkResult:
    input: list[Any]
    evaluations: int
    exhausted: bool  # True if the budget ended the search before a local minimum was reached


def size_of(value: Any) -> int:
    return len(json.dumps(value, separators=(",", ":"), sort_keys=True))


def _magnitude(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, int | float):
        return abs(value)
    if isinstance(value, list):
        return sum(_magnitude(v) for v in value)
    if isinstance(value, dict):
        return sum(_magnitude(v) for v in value.values())
    return 0.0


def complexity(value: Any) -> tuple[int, float]:
    """Smaller is simpler: shorter JSON first, then smaller numeric magnitude."""
    return size_of(value), _magnitude(value)


def _key(value: Any) -> str:
    return json.dumps(value, sort_keys=True)


# ---- candidate generation (pure) ----


def _chunk_removals(n: int) -> Iterator[tuple[int, int]]:
    """(start, end) ranges to delete: halves, then quarters, ..., then single elements."""
    parts = 2
    while True:
        size = max(1, -(-n // parts))  # ceil(n / parts)
        for start in range(0, n, size):
            yield start, min(n, start + size)
        if size == 1:
            return
        parts *= 2


def _int_candidates(v: int) -> Iterator[int]:
    """0 first, then moves toward zero with geometrically shrinking steps (half, quarter, ..., 1),
    so a boundary value is found in a few rounds instead of one step at a time."""
    if v == 0:
        return
    sign = 1 if v > 0 else -1
    seen = {v}
    ordered = [0]
    step = abs(v) // 2
    while step >= 1:
        ordered.append(v - sign * step)
        step //= 2
    ordered.append(v - sign)
    for c in ordered:
        if c not in seen:
            seen.add(c)
            yield c


def candidates(value: Any) -> Iterator[Any]:
    """Smaller variants of one JSON value, most aggressive first. Never yields `value` itself."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        yield from _int_candidates(value)
    elif isinstance(value, float):
        for c in (0.0, float(int(value)), value / 2):
            if c != value:
                yield c
    elif isinstance(value, str):
        for start, end in _chunk_removals(len(value)):
            yield value[:start] + value[end:]
        if value and set(value) != {"a"}:
            yield "a" * len(value)  # simplify everything toward 'a' at once
        for i, ch in enumerate(value):
            if ch != "a":
                yield value[:i] + "a" + value[i + 1 :]
    elif isinstance(value, list):
        for start, end in _chunk_removals(len(value)):
            yield value[:start] + value[end:]
        for i, element in enumerate(value):
            for c in candidates(element):
                yield value[:i] + [c] + value[i + 1 :]
    elif isinstance(value, dict):
        for k in list(value):
            yield {kk: vv for kk, vv in value.items() if kk != k}
        for k, v in value.items():
            for c in candidates(v):
                yield {**value, k: c}


def _arg_candidates(args: list[Any]) -> Iterator[list[Any]]:
    """Candidates for the whole argument list, interleaved across parameters so every parameter
    gets a share of each round's limited batch."""

    def stream(i: int, param: Any) -> Iterator[list[Any]]:
        for c in candidates(param):
            yield args[:i] + [c] + args[i + 1 :]

    streams = [stream(i, param) for i, param in enumerate(args)]
    for group in zip_longest(*streams):
        for candidate in group:
            if candidate is not None:
                yield candidate


# ---- the search ----


async def shrink(
    failing_input: list[Any],
    still_fails: StillFails,
    validate: Validate,
    budget: Budget | None = None,
    *,
    validate_batch: ValidateBatch | None = None,
) -> ShrinkResult:
    """Returns the smallest failing input found. Candidates that `validate` rejects are never run.

    `validate` is a cheap synchronous check. `validate_batch` is an optional asynchronous second
    check (for example the reference module's own validate(args) running in the sandbox); it is
    applied to each round's candidates before they are evaluated and is not counted as evaluations.

    Each round tries a batch of candidates in parallel and moves to the smallest one that still
    fails. Stops at a local minimum, or when the budget (150 evaluations / 15 s) is spent.
    """
    budget = budget or Budget()
    budget.start()
    current = failing_input
    tried: set[str] = {_key(current)}
    exhausted = False

    while True:
        if budget.exhausted:
            exhausted = True
            break
        limit = min(MAX_BATCH, budget.remaining_evaluations)
        batch: list[list[Any]] = []
        for candidate in _arg_candidates(current):
            key = _key(candidate)
            if key in tried:
                continue
            tried.add(key)
            if not validate(candidate):
                continue
            batch.append(candidate)
            if len(batch) >= limit:
                break
        if batch and validate_batch is not None:
            accepted = await validate_batch(batch)
            batch = [c for c, ok in zip(batch, accepted, strict=True) if ok]
            if not batch:
                continue  # every candidate of this round was invalid; try the next ones
        if not batch:
            break  # nothing left to try: current is a local minimum
        flags = await still_fails(batch)
        budget.evaluations += len(batch)
        failing = [c for c, f in zip(batch, flags, strict=True) if f]
        if failing:
            current = min(failing, key=complexity)

    return ShrinkResult(current, budget.evaluations, exhausted)
