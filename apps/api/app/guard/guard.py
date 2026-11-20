import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from app.config import Settings
from app.guard.heuristics import check_heuristics
from app.guard.llm_judge import Judge, JudgeInput
from app.guard.safe_hints import safe_hint
from app.schemas.hint import ProblemContext

logger = logging.getLogger("aporia.guard")


@dataclass
class GuardDecision:
    leaks: bool
    stage: Literal["heuristics", "judge", "none"] = "none"
    severity: str = "none"
    reasons: list[str] = field(default_factory=list)
    similarity: float = 0.0
    judge_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "leaks": self.leaks,
            "stage": self.stage,
            "severity": self.severity,
            "reasons": self.reasons,
            "similarity": round(self.similarity, 3),
            "judge_used": self.judge_used,
        }


async def check(
    draft: str,
    level: int,
    problem: ProblemContext,
    reference_source: str | None,
    judge: Judge,
    failing_case: dict[str, Any] | None = None,
) -> GuardDecision:
    """Heuristics first (cheap, deterministic); the LLM judge runs only if they pass.

    Raises if the judge fails: the caller must treat any exception as "cannot approve".
    """
    heuristic = check_heuristics(draft, level, reference_source, failing_case)
    if heuristic.blocked:
        return GuardDecision(
            leaks=True,
            stage="heuristics",
            severity="partial",
            reasons=heuristic.reasons,
            similarity=heuristic.similarity,
        )
    verdict = await judge(
        JudgeInput(
            draft=draft,
            level=level,
            title=problem.title,
            difficulty=problem.difficulty,
            tags=problem.tags,
            content_text=problem.content_text,
            reference_source=reference_source,
            failing_case=failing_case,
        )
    )
    return GuardDecision(
        leaks=verdict.is_leak,
        stage="judge",
        severity=verdict.severity,
        reasons=[verdict.reason] if verdict.reason else [],
        similarity=heuristic.similarity,
        judge_used=True,
    )


@dataclass
class GuardedResult:
    text: str
    decision: dict[str, Any]
    rewrite_count: int
    used_safe_hint: bool


Generate = Callable[[str | None], Awaitable[str]]
Check = Callable[[str], Awaitable[GuardDecision]]


def _feedback(decision: GuardDecision) -> str:
    reason = "; ".join(decision.reasons) or "it revealed too much"
    return (
        f"Your previous draft was rejected because: {reason}. Write a new reply for the same "
        "level that does not do that. Do not mention this note."
    )


async def guarded_reply(
    generate: Generate, check_draft: Check, *, slug: str, level: int
) -> GuardedResult:
    """Leak policy: generate, check; on a leak regenerate once with the violation fed back; if it
    still leaks, or the guard (or the regeneration) fails, return the deterministic safe hint.
    A draft is never returned without having passed `check_draft`."""
    safe = safe_hint(slug, level)
    draft = await generate(None)  # a generation failure propagates: the caller reports an error
    try:
        first = await check_draft(draft)
    except Exception as exc:  # noqa: BLE001 - guard failure must fail safe
        logger.error("guard failed on first draft: %s", type(exc).__name__)
        return GuardedResult(
            safe, {"error": type(exc).__name__, "safe_hint": True}, 0, used_safe_hint=True
        )
    if not first.leaks:
        return GuardedResult(draft, first.to_dict(), 0, used_safe_hint=False)

    try:
        redraft = await generate(_feedback(first))
        second = await check_draft(redraft)
    except Exception as exc:  # noqa: BLE001
        logger.error("guard failed on rewrite: %s", type(exc).__name__)
        decision = {"first": first.to_dict(), "error": type(exc).__name__, "safe_hint": True}
        return GuardedResult(safe, decision, 1, used_safe_hint=True)
    if not second.leaks:
        return GuardedResult(
            redraft, {**second.to_dict(), "first": first.to_dict()}, 1, used_safe_hint=False
        )
    decision = {"first": first.to_dict(), "second": second.to_dict(), "safe_hint": True}
    return GuardedResult(safe, decision, 1, used_safe_hint=True)


def guard_enabled(settings: Settings, disable_header: str | None) -> bool:
    """The guard can only be switched off for evaluation: header honoured iff APORIA_ENV=eval."""
    return not (settings.aporia_env == "eval" and disable_header == "1")
