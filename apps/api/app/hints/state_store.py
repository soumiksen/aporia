import json
import logging
from dataclasses import asdict
from typing import Any

from app.hints.ladder import LadderState

logger = logging.getLogger("aporia.ladder")

TTL_SECONDS = 12 * 60 * 60


def state_key(device_hash: str, slug: str) -> str:
    return f"ladder:{device_hash}:{slug}"


async def load_state(redis: Any, device_hash: str, slug: str) -> LadderState:
    """Loads the ladder state; any Redis or decoding problem yields a fresh state."""
    try:
        raw = await redis.get(state_key(device_hash, slug))
        if not raw:
            return LadderState()
        data = json.loads(raw)
        return LadderState(
            level_reached=int(data.get("level_reached", 0)),
            attempts_since_hint=int(data.get("attempts_since_hint", 0)),
            last_verdict=data.get("last_verdict"),
        )
    except Exception:  # noqa: BLE001 - state loss must never break a hint request
        logger.warning("ladder state unavailable; starting fresh")
        return LadderState()


async def save_state(redis: Any, device_hash: str, slug: str, state: LadderState) -> None:
    try:
        await redis.set(state_key(device_hash, slug), json.dumps(asdict(state)), ex=TTL_SECONDS)
    except Exception:  # noqa: BLE001
        logger.warning("could not save ladder state")
