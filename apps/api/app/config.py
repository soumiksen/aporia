from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../../.env"), extra="ignore")

    database_url: str = "postgresql+asyncpg://aporia:aporia@localhost:5432/aporia"
    redis_url: str = "redis://localhost:6379/0"
    judge0_url: str = "http://localhost:2358"
    aporia_env: str = "dev"

    # Model names come only from env vars; never hardcode a model name in code.
    aporia_model_fast: str = ""
    aporia_model_strong: str = ""
    aporia_model_judge: str = ""
    aporia_llm_mock: bool = False

    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = ""
    aporia_trace_code: bool = False

    rate_limit_per_minute: int = 30


@lru_cache
def _cached_settings() -> Settings:
    return Settings()


def get_settings() -> Settings:
    """Settings are cached; tests call `reset_settings()` after changing the environment."""
    return _cached_settings()


def reset_settings() -> None:
    _cached_settings.cache_clear()
