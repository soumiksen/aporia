"""Helpers shared by the ml/ scripts. Pure Python; heavy libraries are imported lazily elsewhere."""

import sys
from pathlib import Path
from typing import Any

ML_DIR = Path(__file__).resolve().parent
ROOT = ML_DIR.parent
API_DIR = ROOT / "apps" / "api"
if str(API_DIR) not in sys.path:
    sys.path.insert(0, str(API_DIR))  # the ml scripts reuse app code (guard format, pipeline)


def load_ml_prompt(name: str) -> tuple[str, str]:
    """(system, user_template) from `ml/prompts/<name>.md`, same layout as app/prompts."""
    text = (ML_DIR / "prompts" / f"{name}.md").read_text(encoding="utf-8")
    _, _, rest = text.partition("## SYSTEM")
    system, _, user = rest.partition("## USER")
    return system.strip(), user.strip()


def render(template: str, values: dict[str, Any]) -> str:
    from app.llm.prompts import render as app_render

    return app_render(template, values)
