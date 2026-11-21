import pytest
from sqlalchemy import select

from app.learner.bkt import BKTParams, predict_correct, update
from app.learner.describe import describe_failure
from app.learner.service import (
    overlapping,
    record_attempt,
    record_mistake,
    weak_concepts,
)
from app.models import Mistake, Problem, ProblemSummary
from app.rag.embedder import FakeEmbedder

P = BKTParams()  # 0.2 init, 0.15 learn, 0.2 guess, 0.1 slip


def test_bkt_correct_hand_computed() -> None:
    # evidence = 0.2*0.9 + 0.8*0.2 = 0.34; posterior = 0.18/0.34 = 0.529411...;
    # next = 0.529411 + 0.470588*0.15 = 0.6
    assert update(0.2, True, P) == pytest.approx(0.6, abs=1e-9)


def test_bkt_incorrect_hand_computed() -> None:
    # evidence = 0.2*0.1 + 0.8*0.8 = 0.66; posterior = 0.02/0.66 = 0.030303...;
    # next = 0.030303 + 0.969697*0.15 = 0.175757...
    assert update(0.2, False, P) == pytest.approx(0.17575757575, abs=1e-9)


def test_bkt_predict_correct_hand_computed() -> None:
    assert predict_correct(0.2, P) == pytest.approx(0.2 * 0.9 + 0.8 * 0.2)  # 0.34
    assert predict_correct(1.0, P) == pytest.approx(0.9)
    assert predict_correct(0.0, P) == pytest.approx(0.2)


def test_bkt_properties() -> None:
    p = 0.2
    for _ in range(10):
        nxt = update(p, True, P)
        assert nxt > p  # correct answers raise p_known
        p = nxt
    assert 0.9 < p < 1.0
    assert update(0.0, True, P) == pytest.approx(0.15)  # learning can still happen
    assert 0 < update(0.5, False, P) < update(0.5, True, P) < 1


@pytest.mark.parametrize(
    ("kind", "inp", "expected"),
    [
        ("wrong_answer", [[3]], "Returns a wrong answer when the array has one element."),
        ("runtime_error", [[]], "Crashes when the array is empty."),
        (
            "wrong_answer",
            [[2, 2, 2]],
            "Returns a wrong answer when the array has three elements and all elements of the array are equal.",  # noqa: E501
        ),
        (
            "timeout",
            [[1, -1], 0],
            "Runs too slowly when the array has two elements and the array has negative numbers.",
        ),
        ("wrong_answer", ["", 4], "Returns a wrong answer when the string is empty."),
        ("wrong_answer", [[5, 9, 12, 20, 33]], "Returns a wrong answer on a small input."),
        (None, [[7]], "Fails when the array has one element."),
    ],
)
def test_describe_failure(kind, inp, expected) -> None:
    assert describe_failure(kind, inp) == expected


@pytest.fixture
async def seeded(db_session_factory):
    async with db_session_factory() as s:
        for slug in ("p1", "p2"):
            s.add(Problem(slug=slug, title=slug, difficulty="Easy", tags=[], supported=False))
        await s.flush()
        s.add(ProblemSummary(slug="p1", summary="s", concepts=["sliding-window", "two-pointers"]))
        s.add(ProblemSummary(slug="p2", summary="s", concepts=["sliding-window"]))
        await s.commit()
    return db_session_factory


async def test_record_attempt_updates_each_concept(seeded) -> None:
    async with seeded() as s:
        out = await record_attempt(s, "dev", "p1", "Wrong Answer")
        assert out == {
            "sliding-window": pytest.approx(0.1757575),
            "two-pointers": pytest.approx(0.1757575),
        }
        again = await record_attempt(s, "dev", "p2", "Accepted")
        assert again["sliding-window"] > out["sliding-window"]
        assert await record_attempt(s, "dev", "unknown-problem", "Accepted") == {}


async def test_weak_concepts_needs_two_observations_and_sorts(seeded) -> None:
    async with seeded() as s:
        await record_attempt(s, "dev", "p1", "Wrong Answer")  # both n_obs=1
        assert await weak_concepts(s, "dev") == []
        await record_attempt(s, "dev", "p2", "Wrong Answer")  # sliding-window n_obs=2
        weak = await weak_concepts(s, "dev")
        assert [c for c, _ in weak] == ["sliding-window"]
        await record_attempt(s, "dev", "p1", "Wrong Answer")
        weak = await weak_concepts(s, "dev", k=1)
        assert weak[0][0] == "sliding-window"  # lowest p_known (most failures)
        assert await weak_concepts(s, "someone-else") == []
        assert overlapping(weak, ["sliding-window", "x"]) == ["sliding-window"]


async def test_mistakes_store_description_only_dedupe_and_resolve(seeded) -> None:
    emb = FakeEmbedder()
    async with seeded() as s:
        first = await record_mistake(
            s, emb, "dev", "p1", "sliding-window", "Crashes when the array is empty."
        )
        assert first and first.embedding and not first.resolved
        assert (
            await record_mistake(
                s, emb, "dev", "p1", "sliding-window", "Crashes when the array is empty."
            )
            is None
        )
        await record_mistake(
            s, emb, "dev", "p2", "sliding-window", "Crashes when the array is empty."
        )
        await record_attempt(s, "dev", "p1", "Accepted")
        rows = {m.problem_slug: m.resolved for m in (await s.scalars(select(Mistake))).all()}
        assert rows == {"p1": True, "p2": False}  # only the accepted problem's mistake resolves
