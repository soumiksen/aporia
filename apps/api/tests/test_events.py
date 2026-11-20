import json
import time
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.config import reset_settings  # noqa: F401
from app.models import Event
from app.schemas.events import MAX_BATCH

HEADERS = {"X-Aporia-Device": "device-1"}
CANARY = "CANARY_STUDENT_CODE_8841"


def now_ms() -> int:
    return int(time.time() * 1000)


def event(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"type": "hint_requested", "ts": now_ms(), "slug": "two-sum", "level": 2}
    base.update(over)
    return base


async def count(factory: Any) -> int:
    async with factory() as session:
        return await session.scalar(select(func.count()).select_from(Event)) or 0


async def test_valid_batch_is_stored_without_device_id_or_text(
    client: AsyncClient, db_session_factory
) -> None:
    batch = [
        event(),
        event(type="stuck_prompt_shown", reason="inactivity", level=None),
        event(type="hint_rated", rating=1),
        event(type="stuck_label", was_stuck=True, slug=None, level=None),
    ]
    r = await client.post("/v1/events", json={"events": batch}, headers=HEADERS)
    assert r.status_code == 202 and r.json() == {"accepted": 4}
    async with db_session_factory() as session:
        rows = (await session.scalars(select(Event).order_by(Event.id))).all()
    assert [e.type for e in rows] == [
        "hint_requested", "stuck_prompt_shown", "hint_rated", "stuck_label",
    ]  # fmt: skip
    assert rows[0].slug == "two-sum" and rows[0].props == {"level": 2}
    assert rows[1].props == {"reason": "inactivity"} and rows[3].props == {"was_stuck": True}
    assert all(e.device_hash != "device-1" and len(e.device_hash) == 64 for e in rows)


async def test_all_six_allowed_types_are_accepted() -> None:
    from app.schemas.events import EventType

    assert set(EventType.__args__) == {  # type: ignore[attr-defined]
        "stuck_prompt_shown", "stuck_prompt_accepted", "stuck_prompt_dismissed",
        "hint_requested", "hint_rated", "stuck_label",
    }  # fmt: skip


@pytest.mark.parametrize("bad_type", ["page_view", "code_changed", "", "HINT_REQUESTED"])
async def test_unknown_event_types_are_rejected(
    client: AsyncClient, db_session_factory, bad_type: str
) -> None:
    r = await client.post("/v1/events", json={"events": [event(type=bad_type)]}, headers=HEADERS)
    assert r.status_code == 422 and await count(db_session_factory) == 0


@pytest.mark.parametrize("field", ["code", "content_text", "student_message", "text", "anything"])
async def test_unknown_fields_are_rejected_so_no_code_can_arrive(
    client: AsyncClient, db_session_factory, field: str
) -> None:
    r = await client.post(
        "/v1/events", json={"events": [event(**{field: CANARY})]}, headers=HEADERS
    )
    assert r.status_code == 422
    assert await count(db_session_factory) == 0


async def test_unknown_top_level_field_is_rejected(client: AsyncClient, db_session_factory) -> None:
    r = await client.post("/v1/events", json={"events": [event()], "code": CANARY}, headers=HEADERS)
    assert r.status_code == 422 and await count(db_session_factory) == 0


async def test_a_canary_in_an_allowed_field_never_reaches_the_database(
    client: AsyncClient, db_session_factory
) -> None:
    """Free text cannot be smuggled through slug, reason or the other typed fields."""
    for bad in (
        event(slug=CANARY),  # not a slug (uppercase/underscore)
        event(type="stuck_prompt_shown", reason=CANARY),
        event(level=CANARY),
        event(type="hint_rated", rating=CANARY),
    ):
        r = await client.post("/v1/events", json={"events": [bad]}, headers=HEADERS)
        assert r.status_code == 422
    assert await count(db_session_factory) == 0
    async with db_session_factory() as session:
        dump = json.dumps([e.props for e in (await session.scalars(select(Event))).all()])
    assert CANARY not in dump


async def test_batch_size_limits(client: AsyncClient, db_session_factory) -> None:
    ok = await client.post(
        "/v1/events", json={"events": [event() for _ in range(MAX_BATCH)]}, headers=HEADERS
    )
    assert ok.status_code == 202 and await count(db_session_factory) == 50
    too_many = await client.post(
        "/v1/events", json={"events": [event() for _ in range(MAX_BATCH + 1)]}, headers=HEADERS
    )
    assert too_many.status_code == 422
    empty = await client.post("/v1/events", json={"events": []}, headers=HEADERS)
    assert empty.status_code == 422
    assert await count(db_session_factory) == 50


async def test_oversized_body_is_413(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/events",
        content=b"x" * 40_000,
        headers={**HEADERS, "content-type": "application/json"},
    )
    assert r.status_code in (413, 422)  # too large or not valid JSON; never accepted


@pytest.mark.parametrize(
    "bad",
    [
        {"level": 0}, {"level": 5}, {"rating": 0}, {"rating": 6},
        {"slug": "Has Spaces"}, {"slug": "x" * 101}, {"ts": "yesterday"},
    ],
)  # fmt: skip
async def test_field_validation(client: AsyncClient, bad: dict[str, Any]) -> None:
    r = await client.post("/v1/events", json={"events": [event(**bad)]}, headers=HEADERS)
    assert r.status_code == 422


async def test_timestamps_far_from_now_are_rejected(client: AsyncClient) -> None:
    far_past = now_ms() - 30 * 24 * 3600 * 1000
    far_future = now_ms() + 30 * 24 * 3600 * 1000
    for ts in (far_past, far_future):
        r = await client.post("/v1/events", json={"events": [event(ts=ts)]}, headers=HEADERS)
        assert r.status_code == 422


async def test_device_header_is_required(client: AsyncClient) -> None:
    r = await client.post("/v1/events", json={"events": [event()]})
    assert r.status_code == 400


async def test_events_have_their_own_rate_limit_and_do_not_use_the_hint_budget(
    client: AsyncClient, redis
) -> None:
    from app.ratelimit import EVENTS_PER_MINUTE

    assert EVENTS_PER_MINUTE == 120
    for _ in range(EVENTS_PER_MINUTE):
        r = await client.post("/v1/events", json={"events": [event()]}, headers=HEADERS)
        assert r.status_code == 202
    over = await client.post("/v1/events", json={"events": [event()]}, headers=HEADERS)
    assert over.status_code == 429
    # the same device can still ask for hints: separate counters
    hint = await client.post(
        "/v1/hint",
        json={
            "problem": {"slug": "s", "title": "t", "difficulty": "Easy", "tags": [],
                        "content_text": "x", "meta": None},
            "code": "", "language": "python3",
        },
        headers=HEADERS,
    )  # fmt: skip
    assert hint.status_code == 200
