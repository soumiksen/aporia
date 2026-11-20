import json
from datetime import UTC, datetime
from typing import Any

import fakeredis
import httpx

from app.config import Settings
from app.models import Event
from app.telemetry.posthog import BATCH_SIZE, CURSOR_KEY, forward_events, to_posthog


def settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


async def add_events(factory: Any, n: int) -> None:
    async with factory() as session:
        for i in range(n):
            session.add(
                Event(
                    device_hash="h" * 64,
                    type="hint_requested",
                    slug="two-sum",
                    props={"level": (i % 4) + 1},
                    ts=datetime(2026, 11, 20, 12, 0, i % 60, tzinfo=UTC),
                )
            )
        await session.commit()


def recorder(status: int = 200) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"status": "Ok"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), seen


async def test_nothing_happens_without_a_key(db_session_factory) -> None:
    await add_events(db_session_factory, 3)
    client, seen = recorder()
    redis = fakeredis.FakeAsyncRedis()
    assert await forward_events(db_session_factory, redis, settings(), client) == 0
    assert seen == [] and await redis.get(CURSOR_KEY) is None


async def test_events_are_forwarded_once_and_the_cursor_advances(db_session_factory) -> None:
    await add_events(db_session_factory, 3)
    client, seen = recorder()
    redis = fakeredis.FakeAsyncRedis()
    cfg = settings(posthog_api_key="phc_test", posthog_host="https://ph.example/")
    assert await forward_events(db_session_factory, redis, cfg, client) == 3
    assert str(seen[0].url) == "https://ph.example/batch/"
    body = json.loads(seen[0].content)
    assert body["api_key"] == "phc_test" and len(body["batch"]) == 3
    first = body["batch"][0]
    assert first["event"] == "hint_requested" and first["distinct_id"] == "h" * 64
    assert first["properties"]["slug"] == "two-sum" and first["properties"]["level"] == 1
    assert int(await redis.get(CURSOR_KEY)) == 3  # type: ignore[arg-type]
    # a second run has nothing new to send
    assert await forward_events(db_session_factory, redis, cfg, client) == 0
    assert len(seen) == 1
    await add_events(db_session_factory, 2)
    assert await forward_events(db_session_factory, redis, cfg, client) == 2


async def test_a_failure_keeps_the_cursor_so_the_batch_is_retried(db_session_factory) -> None:
    await add_events(db_session_factory, 2)
    redis = fakeredis.FakeAsyncRedis()
    cfg = settings(posthog_api_key="phc_test")
    bad, _ = recorder(status=503)
    assert await forward_events(db_session_factory, redis, cfg, bad) == 0
    assert await redis.get(CURSOR_KEY) is None
    good, seen = recorder()
    assert await forward_events(db_session_factory, redis, cfg, good) == 2
    assert len(seen) == 1


async def test_large_backlogs_are_sent_in_batches(db_session_factory) -> None:
    await add_events(db_session_factory, BATCH_SIZE + 20)
    client, seen = recorder()
    redis = fakeredis.FakeAsyncRedis()
    total = await forward_events(db_session_factory, redis, settings(posthog_api_key="k"), client)
    assert total == BATCH_SIZE + 20 and len(seen) == 2
    assert [len(json.loads(r.content)["batch"]) for r in seen] == [BATCH_SIZE, 20]


async def test_forwarded_payload_contains_only_stored_event_fields(db_session_factory) -> None:
    await add_events(db_session_factory, 1)
    async with db_session_factory() as session:
        from sqlalchemy import select

        event = (await session.scalars(select(Event))).one()
    payload = to_posthog(event)
    assert set(payload) == {"event", "distinct_id", "timestamp", "properties"}
    assert set(payload["properties"]) <= {"$lib", "slug", "level", "reason", "rating", "was_stuck"}


def test_the_cron_job_is_only_registered_with_a_key(monkeypatch) -> None:
    import importlib

    import app.config as config
    import app.worker as worker

    try:
        monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
        config.reset_settings()
        assert importlib.reload(worker).WorkerSettings.cron_jobs == []
        monkeypatch.setenv("POSTHOG_API_KEY", "phc_test")
        config.reset_settings()
        assert len(importlib.reload(worker).WorkerSettings.cron_jobs) == 1
    finally:
        monkeypatch.delenv("POSTHOG_API_KEY", raising=False)
        config.reset_settings()
        importlib.reload(worker)
