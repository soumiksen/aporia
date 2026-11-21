from typing import Any

import fakeredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.api.hint import get_retriever
from app.config import Settings, reset_settings
from app.db import get_session_factory
from app.guard.classifier import reset_classifier
from app.llm import calls as llm_calls
from app.llm.budget import reset_budget_cache
from app.llm.router import reset_router
from app.main import app
from app.models import Base
from app.ratelimit import get_redis
from app.reference.queue import get_enqueue, get_enqueue_summary
from app.sandbox.base import SandboxError
from app.sandbox.fake import FakeRunner
from app.sandbox.provider import get_runner


async def _discard(rec: llm_calls.CallRecord) -> None:
    return None


@pytest.fixture(autouse=True)
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs in mock mode with no keys and no network."""
    # Tests never read a developer's real .env (it may hold model names and API keys).
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.setenv("APORIA_LLM_MOCK", "1")
    monkeypatch.setenv("APORIA_ENV", "dev")
    monkeypatch.setenv("HINT_CACHE_TTL_S", "0")  # tests that exercise the cache turn it on
    monkeypatch.setenv("APORIA_DAILY_BUDGET_USD", "0")
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
    reset_classifier()
    reset_router()
    reset_budget_cache()
    llm_calls.set_writer(_discard)  # tests never write llm_calls rows to a real database
    yield
    reset_settings()
    reset_classifier()
    reset_router()
    reset_budget_cache()
    llm_calls.set_writer(None)


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
def summary_calls() -> list[tuple[str, dict[str, Any]]]:
    return []


@pytest.fixture
async def client(redis, db_session_factory, enqueue_calls, summary_calls):
    async def fake_enqueue(slug: str, problem: dict[str, Any]) -> bool:
        enqueue_calls.append((slug, problem))
        return True

    app.dependency_overrides[get_session_factory] = lambda: db_session_factory

    async def fake_enqueue_summary(slug: str, problem: dict[str, Any]) -> bool:
        summary_calls.append((slug, problem))
        return True

    app.dependency_overrides[get_enqueue] = lambda: fake_enqueue
    app.dependency_overrides[get_retriever] = lambda: None  # tests opt in with a fake retriever
    app.dependency_overrides[get_enqueue_summary] = lambda: fake_enqueue_summary
    # By default there is no sandbox in tests: grounding degrades to prompt-only.
    no_sandbox = FakeRunner([SandboxError("no sandbox in tests")])
    app.dependency_overrides[get_runner] = lambda: no_sandbox
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.pop(get_session_factory, None)
    app.dependency_overrides.pop(get_enqueue, None)
    app.dependency_overrides.pop(get_enqueue_summary, None)
    app.dependency_overrides.pop(get_retriever, None)
    app.dependency_overrides.pop(get_runner, None)


@pytest.fixture
def llm_records() -> list[llm_calls.CallRecord]:
    """Captures every recorded model call for the test."""
    records: list[llm_calls.CallRecord] = []

    async def collect(rec: llm_calls.CallRecord) -> None:
        records.append(rec)

    llm_calls.set_writer(collect)
    return records
