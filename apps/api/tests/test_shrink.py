import json
import random
from collections.abc import Callable
from typing import Any

import pytest

from app.grounding.shrink import (
    MAX_EVALUATIONS,
    Budget,
    candidates,
    shrink,
    size_of,
)


def predicate(fn: Callable[[list[Any]], bool]):
    """Wraps a pure predicate into the batch `still_fails` the shrinker expects."""
    calls: list[list[Any]] = []

    async def still_fails(batch: list[Any]) -> list[bool]:
        calls.extend(batch)
        return [fn(c) for c in batch]

    still_fails.calls = calls  # type: ignore[attr-defined]
    return still_fails


def always_valid(_: Any) -> bool:
    return True


def locally_minimal(result: list[Any], fn: Callable[[list[Any]], bool], validate=always_valid):
    """No generated candidate of the result both validates and still fails."""
    from app.grounding.shrink import _arg_candidates

    return not any(fn(c) for c in _arg_candidates(result) if validate(c))


async def test_sum_greater_than_ten_shrinks_to_a_minimal_list() -> None:
    def fails(args: list[Any]) -> bool:
        return sum(args[0]) > 10

    result = await shrink([[5, 3, 9, 2, 8, 7, 1]], predicate(fails), always_valid)
    (xs,) = result.input
    assert fails(result.input) and not result.exhausted
    assert len(xs) <= 2  # a single element or an irreducible pair
    assert sum(xs) == 11 or locally_minimal(result.input, fails)
    assert locally_minimal(result.input, fails)  # removing/decreasing anything makes it pass


async def test_string_with_equal_ends_shrinks_to_three_characters() -> None:
    def fails(args: list[Any]) -> bool:
        s = args[0]
        return len(s) >= 3 and s[0] == s[-1]

    result = await shrink(["xyzzyqwertyx"], predicate(fails), always_valid)
    assert result.input == ["aaa"]  # three characters, simplified toward 'a'


async def test_budget_exhaustion_returns_the_best_so_far() -> None:
    fails = lambda args: sum(args[0]) > 10  # noqa: E731
    big = [list(range(1, 40))]
    result = await shrink(big, predicate(fails), always_valid, Budget(max_evaluations=5))
    assert result.exhausted and result.evaluations <= 5
    assert fails(result.input) and size_of(result.input) <= size_of(big)
    full = await shrink(big, predicate(fails), always_valid)
    assert not full.exhausted and size_of(full.input) < size_of(result.input)


async def test_time_budget_returns_the_best_so_far() -> None:
    now = [0.0]

    async def still_fails(batch: list[Any]) -> list[bool]:
        now[0] += 10.0  # every round "takes" 10 seconds
        return [sum(c[0]) > 10 for c in batch]

    budget = Budget(max_seconds=15.0, clock=lambda: now[0])
    result = await shrink([list(range(1, 40))], still_fails, always_valid, budget)
    assert result.exhausted and sum(result.input[0]) > 10  # stopped after 2 rounds, still failing


async def test_default_budget_is_150_evaluations_and_15_seconds() -> None:
    assert MAX_EVALUATIONS == 150
    b = Budget()
    assert b.max_evaluations == 150 and b.max_seconds == 15.0
    evaluations = 0

    async def always_fails_but_nothing_to_shrink(batch: list[Any]) -> list[bool]:
        nonlocal evaluations
        evaluations += len(batch)
        return [False] * len(batch)  # nothing smaller fails

    huge = [[random.Random(1).randint(1, 9) for _ in range(500)]]
    result = await shrink(huge, always_fails_but_nothing_to_shrink, always_valid)
    assert result.evaluations <= 150 and evaluations <= 150


async def test_invalid_candidates_are_never_evaluated() -> None:
    def valid(args: list[Any]) -> bool:
        return len(args[0]) >= 2

    still = predicate(lambda a: sum(a[0]) > 10)
    result = await shrink([[9, 8, 7, 6]], still, valid)
    assert len(result.input[0]) >= 2
    assert all(len(c[0]) >= 2 for c in still.calls)  # type: ignore[attr-defined]


async def test_sign_is_kept_when_validation_requires_it() -> None:
    result = await shrink([-1000], predicate(lambda a: a[0] < -5), lambda a: a[0] < 0)
    assert result.input == [-6]


async def test_multiple_parameters_shrink_independently() -> None:
    def fails(args: list[Any]) -> bool:
        nums, k = args
        return len(nums) >= 2 and k >= 3

    result = await shrink([[4, 8, 15, 16, 23, 42], 100], predicate(fails), always_valid)
    assert result.input == [[0, 0], 3]


async def test_nested_lists_and_dicts() -> None:
    def nested(args: list[Any]) -> bool:
        grid = args[0]
        return any(1 in row for row in grid)

    result = await shrink([[[0, 0, 0], [5, 1, 7], [3, 3, 3]]], predicate(nested), always_valid)
    assert result.input == [[[1]]]

    def dicty(args: list[Any]) -> bool:
        return args[0].get("bad", 0) > 2

    result = await shrink([{"a": 1, "b": 2, "bad": 99}], predicate(dicty), always_valid)
    assert result.input == [{"bad": 3}]


async def test_never_grows_never_mutates_and_is_deterministic() -> None:
    original = [[7, 3, 9, 1, 8]]
    snapshot = json.dumps(original)
    fails = lambda a: sum(a[0]) > 12  # noqa: E731
    first = await shrink(original, predicate(fails), always_valid)
    second = await shrink(original, predicate(fails), always_valid)
    assert json.dumps(original) == snapshot  # input untouched
    assert first.input == second.input and size_of(first.input) <= size_of(original)


async def test_a_non_failing_neighbourhood_returns_the_input_unchanged() -> None:
    result = await shrink([[1, 2, 3]], predicate(lambda a: a[0] == [1, 2, 3]), always_valid)
    assert result.input == [[1, 2, 3]] and not result.exhausted


@pytest.mark.parametrize("seed", range(25))
async def test_random_inputs_reduce_to_a_single_witness(seed: int) -> None:
    rng = random.Random(seed)
    xs = [rng.randint(-50, 300) for _ in range(rng.randint(1, 60))] + [rng.randint(150, 400)]
    rng.shuffle(xs)
    fails = lambda a: any(x > 100 for x in a[0])  # noqa: E731
    result = await shrink([xs], predicate(fails), always_valid)
    assert result.input == [[101]]  # one element, shrunk to the smallest value that still fails


def test_candidate_generators_are_pure_and_smaller() -> None:
    assert list(candidates(10)) == [0, 5, 8, 9]  # zero, then steps of 5, 2, 1
    assert list(candidates(-7)) == [0, -4, -6]
    assert (
        list(candidates(0)) == [] and list(candidates(True)) == [] and list(candidates(None)) == []
    )
    assert list(candidates("abc"))[:3] == ["c", "a", "ab"] or "ab" in list(candidates("abc"))
    assert "aaa" in list(candidates("xyz"))
    lst = [1, 2, 3, 4]
    out = list(candidates(lst))
    assert lst == [1, 2, 3, 4] and [3, 4] in out and [1, 2] in out and [1, 3, 4] in out
    assert all(c != lst for c in out)
