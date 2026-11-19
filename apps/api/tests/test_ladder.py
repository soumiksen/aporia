import fakeredis
import pytest

from app.hints.ladder import (
    LadderState,
    after_hint,
    next_level,
    with_attempts,
)
from app.hints.state_store import TTL_SECONDS, load_state, save_state, state_key
from app.llm.prompts import load_prompt, render


def S(reached: int = 0, attempts: int = 0) -> LadderState:
    return LadderState(level_reached=reached, attempts_since_hint=attempts)


# (level_reached, requested, failed_attempts, expected)
CASES = [
    # first hint
    (0, None, 0, 1),
    (0, 1, 0, 1),
    (0, 2, 0, 1),  # cannot skip: capped at reached + 1
    (0, 4, 0, 1),
    # sequential escalation by request
    (1, 2, 0, 2),
    (2, 3, 0, 3),
    (3, 4, 0, 4),
    # skipping is capped
    (1, 3, 0, 2),
    (1, 4, 0, 2),
    (2, 4, 0, 3),
    # re-serving lower or the same rung
    (3, 1, 0, 1),
    (3, 3, 0, 3),
    (2, 2, 0, 2),
    (4, 2, 0, 2),
    # no explicit request: current rung, at least 1
    (1, None, 0, 1),
    (3, None, 0, 3),
    # capped at 4
    (4, 4, 0, 4),
    (4, None, 0, 4),
    (4, 9, 0, 4),
    # invalid requests are clamped
    (2, 0, 0, 1),
    (2, -5, 0, 1),
    # auto-escalation after 3 failed attempts since the last hint
    (1, None, 3, 2),
    (1, 1, 3, 2),  # request for L1 is overridden upward
    (1, 2, 3, 2),
    (2, None, 5, 3),
    (0, None, 3, 1),  # nothing served yet: first rung
    (3, None, 3, 4),
    (4, None, 9, 4),  # still capped
    (1, None, 2, 1),  # below the threshold: no escalation
    # out-of-range state is clamped
    (9, None, 0, 4),
    (-3, None, 0, 1),
]


@pytest.mark.parametrize(("reached", "requested", "failed", "expected"), CASES)
def test_next_level_table(reached: int, requested: int | None, failed: int, expected: int) -> None:
    assert next_level(S(reached), requested, failed) == expected


def test_next_level_is_always_in_range() -> None:
    for reached in range(-1, 7):
        for requested in (None, *range(-2, 8)):
            for failed in range(0, 6):
                level = next_level(S(reached), requested, failed)
                assert 1 <= level <= 4


def test_state_attempts_count_toward_escalation() -> None:
    assert next_level(S(1, attempts=3), None, 0) == 2
    assert next_level(S(1, attempts=1), None, 2) == 1


def test_after_hint_and_with_attempts() -> None:
    state = with_attempts(S(1), failed_attempts=4, last_verdict="Wrong Answer")
    assert state == LadderState(1, 4, "Wrong Answer")
    served = after_hint(state, 2)
    assert served == LadderState(2, 0, "Wrong Answer")
    assert after_hint(served, 1).level_reached == 2  # never goes down
    assert after_hint(served, 99).level_reached == 4
    assert with_attempts(S(1), -3, None).attempts_since_hint == 0


async def test_state_round_trips_in_redis_with_ttl() -> None:
    redis = fakeredis.FakeAsyncRedis()
    assert await load_state(redis, "dev", "two-sum") == LadderState()
    await save_state(redis, "dev", "two-sum", LadderState(2, 1, "TLE"))
    assert await load_state(redis, "dev", "two-sum") == LadderState(2, 1, "TLE")
    assert await load_state(redis, "dev", "other") == LadderState()  # keyed per problem
    ttl = await redis.ttl(state_key("dev", "two-sum"))
    assert 0 < ttl <= TTL_SECONDS == 43_200


async def test_corrupt_or_unavailable_state_falls_back_to_fresh() -> None:
    redis = fakeredis.FakeAsyncRedis()
    await redis.set(state_key("d", "s"), b"not json")
    assert await load_state(redis, "d", "s") == LadderState()

    class Broken:
        async def get(self, *_: object) -> None:
            raise ConnectionError

        async def set(self, *_: object, **__: object) -> None:
            raise ConnectionError

    assert await load_state(Broken(), "d", "s") == LadderState()
    await save_state(Broken(), "d", "s", LadderState(1))  # must not raise


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_level_prompts_state_rules(level: int) -> None:
    system, user = load_prompt(f"hint_l{level}_v1")
    lowered = system.lower()
    assert f"level {level}" in lowered
    assert "untrusted" in lowered
    assert "never" in lowered and "code" in lowered
    assert "exact fix" in lowered
    assert "correct" in lowered  # no confirmation of pasted solutions
    for key in (
        "title",
        "difficulty",
        "tags",
        "content_text",
        "language",
        "code",
        "student_message",
        "feedback",
    ):
        assert "{" + key + "}" in user
    rendered = render(user, {"title": "T", "code": "x = {1}"})
    assert "x = {1}" in rendered
    if level <= 2:
        assert "algorithm" in lowered  # levels 1-2 may not state the approach
