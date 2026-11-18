from collections import defaultdict
from pathlib import Path
from typing import Any

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


class _SafeDict(defaultdict[str, str]):
    """Missing placeholders render as empty strings instead of raising."""

    def __missing__(self, key: str) -> str:
        return ""


def load_prompt(name: str) -> tuple[str, str]:
    """Returns (system, user_template) from `app/prompts/<name>.md`."""
    text = (PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")
    _, _, rest = text.partition("## SYSTEM")
    system, _, user = rest.partition("## USER")
    return system.strip(), user.strip()


def render(template: str, values: dict[str, Any]) -> str:
    safe = _SafeDict(str, {k: str(v) for k, v in values.items()})
    return template.format_map(safe)
