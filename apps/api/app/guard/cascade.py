"""The cascade guard: heuristics, then the classifier, then the LLM judge only when unsure.

    heuristics blocked          -> leak                       path "heuristic"
    p < t_low                   -> pass (no judge call)       path "classifier_pass"
    p > t_high                  -> leak (rewrite path)        path "classifier_block"
    t_low <= p <= t_high        -> the LLM judge decides      path "judge"

Modes (APORIA_GUARD_MODE): `prompted` (heuristics + judge, the Stage 2 guard), `classifier_only`
(heuristics + classifier at one operating point) and `cascade`. The default is `cascade` when a
classifier is available, otherwise `prompted`. The leak policy (rewrite once, then the safe hint)
lives in `guarded_reply` and is the same for every mode.
"""

import logging
from collections.abc import Sequence
from typing import Any, Literal

from app.config import Settings
from app.guard.classifier import LeakClassifier
from app.guard.guard import GuardDecision, check, judge_decision
from app.guard.heuristics import check_heuristics
from app.guard.llm_judge import Judge
from app.schemas.hint import ProblemContext

logger = logging.getLogger("aporia.guard")

Mode = Literal["prompted", "classifier_only", "cascade"]
MODES: tuple[Mode, ...] = ("prompted", "classifier_only", "cascade")


def resolve_mode(settings: Settings, classifier: LeakClassifier | None) -> Mode:
    """The mode to run. Anything that needs a classifier falls back to `prompted` without one."""
    configured = settings.aporia_guard_mode.strip().lower()
    if configured not in ("", *MODES):
        logger.warning("unknown APORIA_GUARD_MODE %r; using the default", configured)
        configured = ""
    if classifier is None:
        return "prompted"
    return configured or "cascade"  # type: ignore[return-value]


def classifier_only_threshold(classifier: LeakClassifier) -> float:
    """The single operating point of classifier_only: the validation threshold that gives the
    best recall at a false-positive rate of at most 5% (`t_fpr5` in the model card)."""
    return float(classifier.card.get("t_fpr5", classifier.t_high))


def route(p: float, t_low: float, t_high: float) -> Literal["pass", "block", "judge"]:
    """Where a classifier probability goes. Exactly t_low or t_high is 'uncertain' (judge)."""
    if p < t_low:
        return "pass"
    if p > t_high:
        return "block"
    return "judge"


async def cascade_check(
    draft: str,
    level: int,
    problem: ProblemContext,
    reference_source: str | None,
    judge: Judge,
    failing_case: dict[str, Any] | None = None,
    sources: Sequence[str] = (),
    *,
    mode: Mode,
    classifier: LeakClassifier | None,
    summary: str = "",
) -> GuardDecision:
    """One guard decision in the given mode. Raises if the judge fails (callers fail safe)."""
    if mode == "prompted" or classifier is None:
        return await check(draft, level, problem, reference_source, judge, failing_case, sources)

    heuristic = check_heuristics(
        draft, level, reference_source, failing_case, problem.content_text, sources
    )
    if heuristic.blocked:
        return GuardDecision(
            leaks=True, stage="heuristics", severity="partial", reasons=heuristic.reasons,
            similarity=heuristic.similarity, path="heuristic",
        )  # fmt: skip

    try:
        text = classifier.build_text(level, summary, reference_source, draft)
        p = classifier.predict_proba([text])[0]
    except Exception as exc:  # noqa: BLE001 - a classifier fault must not weaken the guard
        logger.error("classifier failed (%s); using the judge for this reply", type(exc).__name__)
        return await judge_decision(
            draft, level, problem, reference_source, judge, failing_case, heuristic.similarity
        )

    if mode == "classifier_only":
        leaks = p >= classifier_only_threshold(classifier)
        return GuardDecision(
            leaks=leaks, stage="none", severity="full" if leaks else "none",
            reasons=["classifier_block"] if leaks else [], similarity=heuristic.similarity,
            path="classifier_block" if leaks else "classifier_pass", classifier_p=p,
        )  # fmt: skip

    where = route(p, classifier.t_low, classifier.t_high)
    if where == "pass":
        return GuardDecision(
            leaks=False, stage="none", similarity=heuristic.similarity,
            path="classifier_pass", classifier_p=p,
        )  # fmt: skip
    if where == "block":
        return GuardDecision(
            leaks=True, stage="none", severity="full", reasons=["classifier_block"],
            similarity=heuristic.similarity, path="classifier_block", classifier_p=p,
        )  # fmt: skip
    decision = await judge_decision(
        draft, level, problem, reference_source, judge, failing_case, heuristic.similarity
    )
    decision.classifier_p = p
    return decision
