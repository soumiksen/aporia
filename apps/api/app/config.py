import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
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
    aporia_internal_token: str = ""


def export_provider_keys(files: tuple[str, ...] | str | None) -> None:
    """Copies `*_API_KEY` / `*_API_BASE` entries from the env files into the process environment.

    LiteLLM reads provider keys from `os.environ`, but pydantic settings only load declared
    fields. Real environment variables win (`setdefault`). Nothing else is exported, so model
    names and flags in `.env` still go through `Settings` only.
    """
    if not files:
        return
    for name in (files,) if isinstance(files, str) else files:
        path = Path(name)
        if not path.is_file():
            continue
        for key, value in dotenv_values(path).items():
            if value and key.upper().endswith(("_API_KEY", "_API_BASE")):
                os.environ.setdefault(key, value)


@lru_cache
def _cached_settings() -> Settings:
    export_provider_keys(Settings.model_config.get("env_file"))  # type: ignore[arg-type]
    return Settings()


def get_settings() -> Settings:
    """Settings are cached; tests call `reset_settings()` after changing the environment."""
    return _cached_settings()


def reset_settings() -> None:
    _cached_settings.cache_clear()
