import litellm
import pytest

from app.config import Settings
from app.llm.tracing import CALLBACK, configure_tracing


@pytest.fixture(autouse=True)
def clean_litellm():
    before = (
        list(litellm.success_callback),
        list(litellm.failure_callback),
        litellm.turn_off_message_logging,
    )
    yield
    litellm.success_callback[:] = before[0]
    litellm.failure_callback[:] = before[1]
    litellm.turn_off_message_logging = before[2]


def settings(**kw: object) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_no_callback_without_keys() -> None:
    assert configure_tracing(settings()) is False
    assert CALLBACK not in litellm.success_callback
    assert CALLBACK not in litellm.failure_callback


def test_callback_registered_with_keys_and_code_hidden_by_default() -> None:
    assert configure_tracing(settings(langfuse_public_key="pk", langfuse_secret_key="sk")) is True
    assert CALLBACK in litellm.success_callback
    assert litellm.turn_off_message_logging is True  # student code stays out of traces


def test_code_traced_only_when_opted_in() -> None:
    configure_tracing(
        settings(langfuse_public_key="pk", langfuse_secret_key="sk", aporia_trace_code=True)
    )
    assert litellm.turn_off_message_logging is False


def test_registration_is_idempotent() -> None:
    s = settings(langfuse_public_key="pk", langfuse_secret_key="sk")
    configure_tracing(s)
    configure_tracing(s)
    assert litellm.success_callback.count(CALLBACK) == 1
