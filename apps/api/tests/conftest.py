from typing import Any

import fakeredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings, reset_settings
from app.db import get_session_factory
from app.main import app
from app.models import Base
from app.ratelimit import get_redis
from app.reference.queue import get_enqueue
from app.sandbox.base import SandboxError
from app.sandbox.fake import FakeRunner
from app.sandbox.provider import get_runner


@pytest.fixture(autouse=True)
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs in mock mode with no keys and no network."""
    # Tests never read a developer's real .env (it may hold model names and API keys).
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setenv("APORIA_LLM_MOCK", "1")
    monkeypatch.setenv("APORIA_ENV", "dev")
    # Importing litellm runs python-dotenv, which can pull a developer's real .env (model names,
    # provider keys) into os.environ. Clear everything that could reach a real provider.
    for var in (
        "APORIA_MODEL_FAST",
        "APORIA_MODEL_STRONG",
        "APORIA_MODEL_JUDGE",
        "LANGFUSE_PUBLIC_KEY",
        "LANGFUSE_SECRET_KEY",
        "GEMINI_API_KEY",
        "GOOGLE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        monkeypatch.delenv(var, raising=False)
    reset_settings()
    yield
    reset_settings()


@pytest.fixture
def redis():
    client = fakeredis.FakeAsyncRedis()
    app.dependency_overrides[get_redis] = lambda: client
    yield client
    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
async def db_session_factory():
    """In-memory SQLite with the real models (no Postgres needed)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
def enqueue_calls() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
async def client(redis, db_session_factory, enqueue_calls):
    async def fake_enqueue(slug: str, problem: dict[str, Any]) -> bool:
        enqueue_calls.append((slug, problem))
        return True

    app.dependency_overrides[get_session_factory] = lambda: db_session_factory
    app.dependency_overrides[get_enqueue] = lambda: fake_enqueue
    # By default there is no sandbox in tests: grounding degrades to prompt-only.
    no_sandbox = FakeRunner([SandboxError("no sandbox in tests")])
    app.dependency_overrides[get_runner] = lambda: no_sandbox
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_session_factory, None)
    app.dependency_overrides.pop(get_enqueue, None)
    app.dependency_overrides.pop(get_runner, None)
