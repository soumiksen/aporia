from types import SimpleNamespace
from typing import Any

import pytest
from litellm.router import Router

from app.config import get_settings, reset_settings
from app.llm.gateway import LLMConfigError, stream_completion
from app.llm.router import reset_router, router_config


def chunk(text: str | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


async def test_real_mode_routes_through_the_router_and_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APORIA_LLM_MOCK", "0")
    monkeypatch.setenv("APORIA_MODEL_FAST", "ollama_chat/test-model")
    monkeypatch.setenv("APORIA_LLM_EXTRA_PARAMS", '{"think": false}')
    reset_settings()
    reset_router()
    seen: dict[str, Any] = {}

    async def fake_acompletion(self: Any, **kwargs: Any):
        seen.update(kwargs)

        async def gen():
            for c in (chunk("a"), chunk(None), chunk("b")):
                yield c

        return gen()

    monkeypatch.setattr(Router, "acompletion", fake_acompletion)
    out = [t async for t in stream_completion([{"role": "user", "content": "hi"}])]
    assert out == ["a", "b"]
    assert seen["model"] == "fast" and seen["stream"] is True  # a Router group, not a model string
    config = router_config(get_settings())
    params = config["model_list"][0]["litellm_params"]
    assert params["model"] == "ollama_chat/test-model"
    assert params["think"] is False  # APORIA_LLM_EXTRA_PARAMS reaches the provider call
    assert config["num_retries"] == 4  # provider rate limits are retried with backoff
    reset_router()


async def test_unset_model_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APORIA_LLM_MOCK", "0")
    reset_settings()
    with pytest.raises(LLMConfigError, match="APORIA_MODEL_STRONG"):
        _ = [t async for t in stream_completion([], "APORIA_MODEL_STRONG")]
