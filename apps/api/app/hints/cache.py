"""Hint response cache (Redis, 1 hour by default).

Key: (slug, level, code_hash, failing_case_hash, prompt_version). When the student's own learner
memory was used in the prompt, the device hash is part of the key, so one student's personalised
hint is never served to another. The cache is bypassed whenever the reply could differ for reasons
the key does not capture (a student message, evaluation switches) and a safe-hint fallback is never
cached (it is usually a transient failure).
"""

import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

logger = logging.getLogger("aporia.hint")

KEY_PREFIX = "hintcache:v1"


@dataclass
class CachedHint:
    text: str
    decision: dict[str, Any]
    rewrite_count: int = 0
    sources: list[dict[str, str]] = field(default_factory=list)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def failing_case_hash(failing_case: dict[str, Any] | None) -> str:
    """A stable hash of the failing case (input, expected, actual, kind), or "none"."""
    if not failing_case:
        return "none"
    return sha(json.dumps(failing_case, sort_keys=True, default=str))[:16]


def cache_key(
    slug: str,
    level: int,
    code: str,
    failing_case: dict[str, Any] | None,
    prompt_version: str,
    device: str | None = None,
) -> str:
    """`device` is passed only when learner memory was used in the prompt."""
    parts = [
        KEY_PREFIX,
        slug,
        str(level),
        sha(code)[:16],
        failing_case_hash(failing_case),
        prompt_version,
    ]
    if device:
        parts += ["dev", device[:16]]
    return ":".join(parts)


def should_bypass(
    *,
    guard_on: bool,
    use_rag: bool,
    use_memory: bool,
    student_message: str | None,
    ttl_s: int,
) -> bool:
    """True when the cache must be neither read nor written."""
    return (
        ttl_s <= 0
        or not guard_on  # evaluation runs measure the model, not the cache
        or not use_rag
        or not use_memory
        or bool(student_message and student_message.strip())  # the reply answers that message
    )


async def get_cached(redis: Any, key: str) -> CachedHint | None:
    try:
        raw = await redis.get(key)
        return CachedHint(**json.loads(raw)) if raw else None
    except Exception as exc:  # noqa: BLE001 - a cache outage must not fail a hint
        logger.warning("hint cache read failed: %s", type(exc).__name__)
        return None


async def put_cached(redis: Any, key: str, hint: CachedHint, ttl_s: int) -> None:
    try:
        await redis.set(key, json.dumps(asdict(hint)), ex=ttl_s)
    except Exception as exc:  # noqa: BLE001
        logger.warning("hint cache write failed: %s", type(exc).__name__)
