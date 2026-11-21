import os
from functools import lru_cache
from pathlib import Path
from typing import Any

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
    # LiteLLM retries (with backoff, honouring provider retry hints) for rate limits and 5xx.
    llm_num_retries: int = 4
    grounding_budget_s: float = 12.0  # total wall-clock budget for execution grounding
    aporia_prompt_version: str = "v3"  # hint_l*_<version>.md; v1 is kept for evals
    # Extra provider parameters passed to every LiteLLM call, as JSON, e.g. {"think": false} to
    # switch off reasoning on local Ollama models. Never put secrets here.
    aporia_llm_extra_params: dict[str, Any] = {}
    # RAG. The user supplies the provider model string (e.g. an Ollama or OpenAI embedding model).
    # Vectors shorter than EMBED_DIM are zero-padded (cosine similarity is unchanged).
    aporia_embedding_model: str = ""
    aporia_rerank: bool = False  # cross-encoder rerank (needs `uv sync --group rerank`)
    aporia_require_reviewed_notes: bool = False  # ingest only notes marked reviewed: true
    # Stage 5: the leak classifier and the guard mode.
    aporia_classifier_dir: str = ""  # directory with model.onnx, tokenizer.json, model_card.json
    aporia_guard_mode: str = ""  # prompted | classifier_only | cascade ("" = cascade if a model)
    # Stage 5: routing, caching and cost control.
    aporia_fallbacks_fast: str = ""  # comma-separated fallback model strings per group
    aporia_fallbacks_strong: str = ""
    aporia_fallbacks_judge: str = ""
    llm_timeout_s: float = 60.0
    hint_cache_ttl_s: int = 3600
    aporia_daily_budget_usd: float = 0.0  # 0 = no budget; above it hints fall back to safe hints
    otel_exporter_otlp_endpoint: str = ""  # OpenTelemetry is on only when this is set
    aporia_internal_token: str = ""
    posthog_api_key: str = ""  # forwarding to PostHog is off unless this is set
    posthog_host: str = "https://us.i.posthog.com"
    sentry_dsn: str = ""  # error tracking is off unless this is set


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
