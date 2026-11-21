"""Model routing: a LiteLLM Router with three groups and per-group fallbacks.

    fast    levels 1 and 2 (cheap, quick nudges)       APORIA_MODEL_FAST
    strong  levels 3 and 4, reference building         APORIA_MODEL_STRONG
    judge   the leak judge                             APORIA_MODEL_JUDGE

Fallbacks are comma-separated model strings per group (APORIA_FALLBACKS_FAST / _STRONG / _JUDGE);
each becomes a deployment of its own and is tried, in order, when the primary fails after its
retries. Timeouts and retries come from settings. Model names only ever come from env vars.
"""

import json
from typing import Any, Literal

from app.config import Settings, get_settings

Group = Literal["fast", "strong", "judge"]
GROUPS: tuple[Group, ...] = ("fast", "strong", "judge")
MAX_FAST_LEVEL = 2

_router: Any = None
_router_key: str | None = None


def group_for_level(level: int) -> Group:
    """Small model for levels 1 and 2, strong model for levels 3 and 4."""
    return "fast" if level <= MAX_FAST_LEVEL else "strong"


def model_env_for_group(group: Group) -> str:
    return {
        "fast": "APORIA_MODEL_FAST",
        "strong": "APORIA_MODEL_STRONG",
        "judge": "APORIA_MODEL_JUDGE",
    }[group]


def group_for_model_env(model_env: str) -> Group:
    return {
        "APORIA_MODEL_FAST": "fast",
        "APORIA_MODEL_STRONG": "strong",
        "APORIA_MODEL_JUDGE": "judge",
    }[model_env]  # type: ignore[return-value]


def _models(settings: Settings, group: Group) -> tuple[str, list[str]]:
    primary = {
        "fast": settings.aporia_model_fast,
        "strong": settings.aporia_model_strong,
        "judge": settings.aporia_model_judge,
    }[group]
    raw = {
        "fast": settings.aporia_fallbacks_fast,
        "strong": settings.aporia_fallbacks_strong,
        "judge": settings.aporia_fallbacks_judge,
    }[group]
    return primary, [m.strip() for m in raw.split(",") if m.strip()]


def router_config(settings: Settings) -> dict[str, Any]:
    """The Router constructor arguments for these settings (pure, so it can be tested)."""
    model_list: list[dict[str, Any]] = []
    fallbacks: list[dict[str, list[str]]] = []
    for group in GROUPS:
        primary, extras = _models(settings, group)
        if not primary:
            continue  # an unset group is simply not routable (the gateway reports it clearly)
        names = [group] + [f"{group}_fallback{i}" for i in range(1, len(extras) + 1)]
        for name, model in zip(names, [primary, *extras], strict=True):
            model_list.append(
                {
                    "model_name": name,
                    "litellm_params": {
                        "model": model,
                        "timeout": settings.llm_timeout_s,
                        **settings.aporia_llm_extra_params,
                    },
                }
            )
        if extras:
            fallbacks.append({group: names[1:]})
    return {
        "model_list": model_list,
        "fallbacks": fallbacks,
        "num_retries": settings.llm_num_retries,
        "timeout": settings.llm_timeout_s,
    }


def get_router(settings: Settings | None = None) -> Any:
    """The shared Router, rebuilt when the model configuration changes."""
    global _router, _router_key
    settings = settings or get_settings()
    config = router_config(settings)
    key = json.dumps(config, sort_keys=True, default=str)
    if _router is None or key != _router_key:
        from litellm.router import Router

        _router, _router_key = Router(**config), key
    return _router


def reset_router() -> None:
    global _router, _router_key
    _router, _router_key = None, None
