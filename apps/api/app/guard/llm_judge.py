import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from app.config import get_settings
from app.llm.gateway import resolve_model
from app.llm.prompts import load_prompt, render

logger = logging.getLogger("aporia.guard")

NO_REFERENCE_TEXT = "(none: no verified reference exists; judge against the problem statement only)"


class GuardVerdict(BaseModel):
    leaks: bool
    severity: Literal["none", "partial", "full"]
    reason: str

    @property
    def is_leak(self) -> bool:
        """`partial` and `full` always count as leaks, even if the model forgot to set leaks."""
        return self.leaks or self.severity != "none"


@dataclass(frozen=True)
class JudgeInput:
    draft: str
    level: int
    title: str
    difficulty: str
    tags: list[str]
    content_text: str
    reference_source: str | None


Judge = Callable[[JudgeInput], Awaitable[GuardVerdict]]


def build_judge_messages(inp: JudgeInput) -> list[dict[str, str]]:
    system, template = load_prompt("guard_judge_v1")
    user = render(
        template,
        {
            "level": inp.level,
            "title": inp.title,
            "difficulty": inp.difficulty,
            "tags": ", ".join(inp.tags),
            "content_text": inp.content_text,
            "reference": inp.reference_source or NO_REFERENCE_TEXT,
            "draft": inp.draft,
        },
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def instructor_judge(inp: JudgeInput) -> GuardVerdict:
    """Structured judge call (Instructor over LiteLLM). Raises on failure; callers fail safe."""
    settings = get_settings()
    if settings.aporia_llm_mock:
        return GuardVerdict(leaks=False, severity="none", reason="mock mode (no model call)")

    model = resolve_model("APORIA_MODEL_JUDGE")
    import instructor
    import litellm

    from app.llm.tracing import configure_tracing

    configure_tracing()
    client = instructor.from_litellm(litellm.acompletion)
    return await client.chat.completions.create(  # pyright: ignore[reportCallIssue]
        model=model,
        messages=build_judge_messages(inp),  # pyright: ignore[reportArgumentType]
        response_model=GuardVerdict,
        max_retries=1,
        metadata={"purpose": "leak_judge", "level": inp.level},
    )


def get_judge() -> Judge:
    return instructor_judge
