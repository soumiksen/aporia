import json

import pytest
from httpx import AsyncClient

from app.config import reset_settings
from app.llm.gateway import MOCK_REPLY

HEADERS = {"X-Aporia-Device": "device-1"}


def body(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "problem": {
            "slug": "synthetic-sum",
            "title": "Synthetic Sum",
            "difficulty": "Easy",
            "tags": ["Array"],
            "content_text": "Add two numbers.",
            "meta": None,
        },
        "code": "def add(a, b):\n    return a",
        "language": "python3",
        "level": 1,
        "student_message": None,
    }
    base.update(overrides)
    return base


def parse_sse(text: str) -> list[tuple[str, dict[str, object]]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((lines["event"], json.loads(lines["data"])))
    return events


async def test_streams_tokens_then_done(client: AsyncClient) -> None:
    r = await client.post("/v1/hint", json=body(), headers=HEADERS)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(r.text)
    names = [n for n, _ in events]
    assert names[-1] == "done"
    assert set(names[:-1]) == {"token"} and len(names) > 2
    done = events[-1][1]
    assert done["level"] == 1 and done["sources"] == []
    assert isinstance(done["hint_id"], str) and len(done["hint_id"]) == 36
    assert "".join(str(d["text"]) for n, d in events if n == "token") == MOCK_REPLY
    assert all(len(str(d["text"])) <= 20 for n, d in events if n == "token")  # 20-char chunks


async def test_missing_device_header_is_400(client: AsyncClient) -> None:
    r = await client.post("/v1/hint", json=body())
    assert r.status_code == 400


async def test_oversized_code_is_413(client: AsyncClient) -> None:
    r = await client.post("/v1/hint", json=body(code="x" * 50_001), headers=HEADERS)
    assert r.status_code == 413


async def test_code_at_limit_is_ok(client: AsyncClient) -> None:
    r = await client.post("/v1/hint", json=body(code="x" * 50_000), headers=HEADERS)
    assert r.status_code == 200


async def test_oversized_body_is_413(client: AsyncClient) -> None:
    big = body()
    big["problem"] = {**big["problem"], "content_text": "y" * 300_000}  # type: ignore[dict-item]
    r = await client.post("/v1/hint", json=big, headers=HEADERS)
    assert r.status_code == 413


async def test_invalid_level_is_422(client: AsyncClient) -> None:
    r = await client.post("/v1/hint", json=body(level=9), headers=HEADERS)
    assert r.status_code == 422


async def test_rate_limit_per_device(client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    reset_settings()
    codes = [
        (await client.post("/v1/hint", json=body(), headers=HEADERS)).status_code for _ in range(5)
    ]
    assert codes == [200, 200, 200, 429, 429]
    other = await client.post("/v1/hint", json=body(), headers={"X-Aporia-Device": "device-2"})
    assert other.status_code == 200


async def test_missing_model_without_mock_fails_loudly(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("APORIA_LLM_MOCK", "0")
    reset_settings()
    r = await client.post("/v1/hint", json=body(), headers=HEADERS)
    assert r.status_code == 503
    assert "APORIA_MODEL_FAST" in r.json()["detail"]
