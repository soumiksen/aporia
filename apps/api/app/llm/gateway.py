import asyncio
from collections.abc import AsyncIterator
from typing import Any, Literal

from app.config import get_settings
from app.llm.calls import tracked
from app.llm.router import get_router, group_for_model_env

ModelEnv = Literal["APORIA_MODEL_FAST", "APORIA_MODEL_STRONG", "APORIA_MODEL_JUDGE"]

MOCK_TOKENS = [
    "What ",
    "does ",
    "your ",
    "code ",
    "do ",
    "on ",
    "the ",
    "smallest ",
    "input ",
    "you ",
    "can ",
    "think ",
    "of?",
]


class LLMConfigError(RuntimeError):
    """The model env var is unset and mock mode is off."""


def resolve_model(model_env: ModelEnv) -> str:
    settings = get_settings()
    model = {
        "APORIA_MODEL_FAST": settings.aporia_model_fast,
        "APORIA_MODEL_STRONG": settings.aporia_model_strong,
        "APORIA_MODEL_JUDGE": settings.aporia_model_judge,
    }[model_env]
    if not model:
        raise LLMConfigError(
            f"{model_env} is not set. Set it to a provider model string, or set APORIA_LLM_MOCK=1."
        )
    return model


def ensure_configured(model_env: ModelEnv) -> None:
    """Raises LLMConfigError early (before a stream starts) when a real call cannot be made."""
    if not get_settings().aporia_llm_mock:
        resolve_model(model_env)


async def stream_completion(
    messages: list[dict[str, str]],
    model_env: ModelEnv = "APORIA_MODEL_FAST",
    *,
    metadata: dict[str, Any] | None = None,
) -> AsyncIterator[str]:
    """Yields text deltas. Mock mode makes no network access."""
    if get_settings().aporia_llm_mock:
        for token in MOCK_TOKENS:
            await asyncio.sleep(0.01)
            yield token
        return

    resolve_model(model_env)  # raises a clear error when the group has no model
    from app.llm.tracing import configure_tracing

    configure_tracing()
    # Streaming goes through the Router too (fallbacks, timeouts). Token usage is not reported on a
    # stream, so streamed calls are not written to llm_calls.
    response = await get_router().acompletion(
        model=group_for_model_env(model_env),
        messages=messages,
        stream=True,
        metadata=metadata or {},
    )
    async for chunk in response:  # pyright: ignore[reportGeneralTypeIssues]
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


MOCK_REPLY = "".join(MOCK_TOKENS)


async def complete(
    messages: list[dict[str, str]],
    model_env: ModelEnv = "APORIA_MODEL_FAST",
    *,
    metadata: dict[str, Any] | None = None,
    purpose: str = "hint",
) -> str:
    """Non-streaming completion (the guard needs the whole draft before anything is shown).
    Routed through the Router (fallbacks, timeouts, retries) and recorded in `llm_calls`."""
    if get_settings().aporia_llm_mock:
        return MOCK_REPLY

    model = resolve_model(model_env)

    from app.llm.tracing import configure_tracing

    configure_tracing()
    router = get_router()
    response = await tracked(
        purpose,
        model,
        lambda: router.acompletion(
            model=group_for_model_env(model_env), messages=messages, metadata=metadata or {}
        ),
    )
    content = response.choices[0].message.content  # pyright: ignore[reportAttributeAccessIssue]
    return content or ""
