import fakeredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import reset_settings
from app.main import app
from app.models import Base
from app.ratelimit import get_redis


@pytest.fixture(autouse=True)
def mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test runs in mock mode with no keys and no network."""
    monkeypatch.setenv("APORIA_LLM_MOCK", "1")
    for var in ("APORIA_MODEL_FAST", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"):
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
async def client(redis):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


@pytest.fixture
async def db_session_factory():
    """In-memory SQLite with the real models (no Postgres needed)."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()
