"""Error tracking (Sentry), enabled only when SENTRY_DSN is set, with a privacy scrubber.

Student code and problem text must never leave the server through error reports: request bodies
are dropped, any field named `code`, `content_text` or `student_message` is filtered at any depth,
and local variables are not captured.
"""

import logging
from typing import Any, cast

import sentry_sdk

from app.config import Settings

logger = logging.getLogger("aporia.observability")

FILTERED = "[Filtered]"
SENSITIVE_KEYS = frozenset({"code", "content_text", "student_message"})
SENSITIVE_HEADERS = frozenset({"x-aporia-device", "x-aporia-internal", "authorization", "cookie"})


def scrub(value: Any) -> Any:
    """Recursively replaces the value of every sensitive key (case-insensitive). Pure."""
    if isinstance(value, dict):
        return {
            key: FILTERED if str(key).lower() in SENSITIVE_KEYS else scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [scrub(item) for item in value]
    if isinstance(value, tuple):
        return tuple(scrub(item) for item in value)
    return value


def before_send(event: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any] | None:
    """Sentry `before_send`: no request bodies, no sensitive fields, no identifying headers."""
    cleaned: dict[str, Any] = scrub(event)
    request = cleaned.get("request")
    if isinstance(request, dict):
        request.pop("data", None)  # the body of a hint request is the student's code
        request.pop("cookies", None)
        request.pop("query_string", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            request["headers"] = {
                k: FILTERED if str(k).lower() in SENSITIVE_HEADERS else v
                for k, v in headers.items()
            }
    return cleaned


def before_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any] | None = None) -> dict[str, Any]:
    return scrub(crumb)  # type: ignore[no-any-return]


def init_sentry(settings: Settings, **overrides: Any) -> bool:
    """Initialises Sentry iff a DSN is configured. Returns whether it is active."""
    if not settings.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.aporia_env,
        before_send=cast(Any, before_send),
        before_breadcrumb=cast(Any, before_breadcrumb),
        # What the SDK may collect on its own. Request bodies are the student's code, and frame
        # variables could hold it too; `before_send` above is a second layer of defence.
        data_collection={"user_info": False, "http_bodies": [], "stack_frame_variables": False},
        traces_sample_rate=0.0,
        **overrides,
    )
    return True
