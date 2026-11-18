import os

from app.config import Settings, get_settings

CALLBACK = "langfuse"


def tracing_enabled(settings: Settings) -> bool:
    return bool(settings.langfuse_public_key)


def configure_tracing(settings: Settings | None = None) -> bool:
    """Registers Langfuse through LiteLLM callbacks only when `LANGFUSE_PUBLIC_KEY` is set.

    Returns whether tracing is active. Without keys this does nothing at all.
    Student code stays out of traces unless `APORIA_TRACE_CODE=1`: LiteLLM's message logging
    (prompt and response) is switched off otherwise.
    """
    import litellm

    s = settings or get_settings()
    if not tracing_enabled(s):
        return False

    # The Langfuse SDK reads its configuration from the process environment.
    for name, value in (
        ("LANGFUSE_PUBLIC_KEY", s.langfuse_public_key),
        ("LANGFUSE_SECRET_KEY", s.langfuse_secret_key),
        ("LANGFUSE_HOST", s.langfuse_host),
    ):
        if value:
            os.environ.setdefault(name, value)

    litellm.turn_off_message_logging = not s.aporia_trace_code
    for callbacks in (litellm.success_callback, litellm.failure_callback):
        if CALLBACK not in callbacks:
            callbacks.append(CALLBACK)
    return True
