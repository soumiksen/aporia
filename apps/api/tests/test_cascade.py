from typing import Any

import pytest

from app.config import Settings
from app.guard.cascade import cascade_check, resolve_mode, route
from app.guard.llm_judge import GuardVerdict
from app.schemas.hint import ProblemContext

T_LOW, T_HIGH = 0.2, 0.8
PROBLEM = ProblemContext(
    slug="p", title="P", difficulty="Easy", tags=[], content_text="Count pairs."
)
SAFE = "What does your code return for an empty list?"
LEAKY_CODE = "```python\ndef f(a):\n    x = 1\n    y = 2\n    z = 3\n    return x\n```"


class FakeClassifier:
    def __init__(self, p: float | Exception, card: dict[str, Any] | None = None) -> None:
        self.p = p
        self.t_low, self.t_high = T_LOW, T_HIGH
        self.card = card or {}
        self.texts: list[str] = []

    def build_text(self, level: int, summary: str, reference: str | None, reply: str) -> str:
        return f"{level}|{summary}|{reply}"

    def predict_proba(self, texts: list[str]) -> list[float]:
        self.texts += texts
        if isinstance(self.p, Exception):
            raise self.p
        return [self.p]


class FakeJudge:
    def __init__(self, leaks: bool = False, error: Exception | None = None) -> None:
        self.calls = 0
        self.leaks, self.error = leaks, error

    async def __call__(self, inp: Any) -> GuardVerdict:
        self.calls += 1
        if self.error:
            raise self.error
        return GuardVerdict(
            leaks=self.leaks, severity="full" if self.leaks else "none", reason="judged"
        )


async def run(mode, classifier, judge, draft=SAFE, level=2):
    return await cascade_check(
        draft, level, PROBLEM, None, judge, mode=mode, classifier=classifier, summary="a summary"
    )


@pytest.mark.parametrize(
    ("p", "expected"),
    [
        (0.0, "pass"), (0.1999, "pass"),
        (0.2, "judge"),  # exactly t_low is uncertain
        (0.5, "judge"),
        (0.8, "judge"),  # exactly t_high is uncertain
        (0.8001, "block"), (1.0, "block"),
    ],
)  # fmt: skip
def test_route_boundaries(p, expected) -> None:
    assert route(p, T_LOW, T_HIGH) == expected


@pytest.mark.parametrize(
    ("p", "path", "leaks", "judge_calls"),
    [
        (0.05, "classifier_pass", False, 0),
        (0.95, "classifier_block", True, 0),
        (0.5, "judge", False, 1),
    ],
)
async def test_cascade_paths(p, path, leaks, judge_calls) -> None:
    judge = FakeJudge(leaks=False)
    clf = FakeClassifier(p)
    decision = await run("cascade", clf, judge)
    assert (decision.path, decision.leaks, judge.calls) == (path, leaks, judge_calls)
    assert decision.classifier_p == p
    assert decision.to_dict()["path"] == path and decision.to_dict()["classifier_p"] == p
    assert clf.texts == ["2|a summary|" + SAFE]  # the shared formatter's inputs reach the model


async def test_uncertain_reply_takes_the_judges_verdict() -> None:
    decision = await run("cascade", FakeClassifier(0.5), FakeJudge(leaks=True))
    assert decision.leaks and decision.path == "judge" and decision.judge_used
    assert decision.classifier_p == 0.5


async def test_heuristics_come_first_and_skip_the_classifier() -> None:
    clf, judge = FakeClassifier(0.01), FakeJudge()
    decision = await run("cascade", clf, judge, draft=LEAKY_CODE, level=2)
    assert decision.path == "heuristic" and decision.leaks and decision.stage == "heuristics"
    assert clf.texts == [] and judge.calls == 0


async def test_prompted_mode_never_touches_the_classifier() -> None:
    clf, judge = FakeClassifier(0.99), FakeJudge()
    decision = await run("prompted", clf, judge)
    assert decision.path == "judge" and not decision.leaks and judge.calls == 1 and clf.texts == []


async def test_no_classifier_means_prompted() -> None:
    judge = FakeJudge()
    decision = await run("cascade", None, judge)
    assert decision.path == "judge" and judge.calls == 1


@pytest.mark.parametrize(("p", "leaks"), [(0.39, False), (0.4, True), (0.9, True)])
async def test_classifier_only_uses_the_fpr5_operating_point(p, leaks) -> None:
    clf = FakeClassifier(p, {"t_fpr5": 0.4})
    judge = FakeJudge()
    decision = await run("classifier_only", clf, judge)
    assert decision.leaks is leaks and judge.calls == 0
    assert decision.path == ("classifier_block" if leaks else "classifier_pass")


async def test_classifier_fault_falls_back_to_the_judge() -> None:
    judge = FakeJudge(leaks=True)
    decision = await run("cascade", FakeClassifier(RuntimeError("onnx boom")), judge)
    assert decision.path == "judge" and decision.leaks and judge.calls == 1


async def test_judge_failure_propagates_so_the_caller_fails_safe() -> None:
    with pytest.raises(RuntimeError):
        await run("cascade", FakeClassifier(0.5), FakeJudge(error=RuntimeError("judge down")))


def test_resolve_mode_defaults_and_fallbacks() -> None:
    clf = FakeClassifier(0.5)

    def mode(configured: str, classifier) -> str:
        return resolve_mode(Settings(aporia_guard_mode=configured), classifier)  # type: ignore[arg-type]

    assert mode("", clf) == "cascade"  # default with a model
    assert mode("", None) == "prompted"  # default without one
    assert mode("cascade", None) == "prompted"  # needs a classifier: fall back safely
    assert mode("classifier_only", None) == "prompted"
    assert mode("prompted", clf) == "prompted"
    assert mode("classifier_only", clf) == "classifier_only"
    assert mode("nonsense", clf) == "cascade"


# ---- over HTTP ----


async def test_endpoint_records_the_guard_path(client, db_session_factory, monkeypatch) -> None:
    from sqlalchemy import select

    from app.api.hint import get_generator
    from app.guard.llm_judge import get_judge
    from app.main import app
    from app.models import Hint
    from tests.test_hint_ladder_guard import CLEAN, ScriptedGenerator, ask, done

    judge = FakeJudge()
    app.dependency_overrides[get_generator] = lambda: ScriptedGenerator(CLEAN)
    app.dependency_overrides[get_judge] = lambda: judge
    try:
        monkeypatch.setattr("app.api.hint.get_classifier", lambda: FakeClassifier(0.01))
        events = await ask(client, level=1)
        assert done(events)["level"] == 1 and judge.calls == 0  # the classifier passed it
        monkeypatch.setattr("app.api.hint.get_classifier", lambda: None)  # missing artifacts
        await ask(client, level=1, code="def pairCount(a, t):\n    return 1")
        assert judge.calls == 1  # fell back to the prompted guard
    finally:
        app.dependency_overrides.pop(get_generator, None)
        app.dependency_overrides.pop(get_judge, None)
    async with db_session_factory() as s:
        rows = (await s.scalars(select(Hint).order_by(Hint.created_at))).all()
    assert [r.guard_decision["path"] for r in rows] == ["classifier_pass", "judge"]
    assert rows[0].guard_decision["classifier_p"] == 0.01
