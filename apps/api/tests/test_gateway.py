from types import SimpleNamespace
from typing import Any

import litellm
import pytest

from app.config import reset_settings
from app.llm.gateway import LLMConfigError, stream_completion


def chunk(text: str | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


async def test_real_mode_uses_env_model_and_streams(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APORIA_LLM_MOCK", "0")
    monkeypatch.setenv("APORIA_MODEL_FAST", "provider/test-model")
    monkeypatch.setenv("APORIA_LLM_EXTRA_PARAMS", '{"think": false}')
    reset_settings()
    seen: dict[str, Any] = {}

    async def fake_acompletion(**kwargs: Any):
        seen.update(kwargs)

        async def gen():
            for c in (chunk("a"), chunk(None), chunk("b")):
                yield c

        return gen()

    monkeypatch.setattr(litellm, "acompletion", fake_acompletion)
    out = [t async for t in stream_completion([{"role": "user", "content": "hi"}])]
    assert out == ["a", "b"]
    assert seen["model"] == "provider/test-model" and seen["stream"] is True
    assert seen["num_retries"] == 4  # provider rate limits are retried with backoff
    assert seen["think"] is False  # APORIA_LLM_EXTRA_PARAMS is forwarded to the provider call


async def test_unset_model_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APORIA_LLM_MOCK", "0")
    reset_settings()
    with pytest.raises(LLMConfigError, match="APORIA_MODEL_STRONG"):
        _ = [t async for t in stream_completion([], "APORIA_MODEL_STRONG")]
