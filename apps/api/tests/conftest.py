import fakeredis
import pytest
from httpx import ASGITransport, AsyncClient

from app.config import reset_settings
from app.main import app
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
