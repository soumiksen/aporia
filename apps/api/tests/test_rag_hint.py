from collections.abc import Sequence
from typing import Any

import pytest
from httpx import AsyncClient

from app.api.hint import get_retriever
from app.guard.heuristics import check_heuristics
from app.hints.retrieval_context import RetrievalContext, build_query
from app.learner.service import MistakeHit
from app.main import app
from app.models import Problem, ProblemSummary
from app.rag.retrieve import Hit
from tests.support.modules import PAIR_PROBLEM
from tests.test_hint_ladder_guard import (
    CLEAN,
    HEADERS,
    NONE,
    ScriptedGenerator,
    ScriptedJudge,
    ask,
    done,
    shown,
)

NOTE_TEXT = (
    "Keep a summary of the current stretch and move the left edge only when the rule is "
    "broken so each item enters and leaves the stretch once"
)
NOTES = [
    Hit("notes", "sliding-window", NOTE_TEXT, "Idea"),
    Hit(
        "notes", "two-pointers", "Move whichever pointer the comparison allows.", "When it applies"
    ),
]
MISTAKES = [MistakeHit(7, "sliding-window", "Returns a wrong answer when the array is empty.", 0.8)]
ANALOGOUS = [
    Hit(
        "problems",
        "other-problem",
        "Track a valid stretch while scanning.",
        concepts=["sliding-window"],
    )
]


class FakeRetriever:
    def __init__(self, context: RetrievalContext | Exception) -> None:
        self.context = context
        self.gathered: list[dict[str, Any]] = []
        self.remembered: list[dict[str, Any]] = []

    async def gather(self, **kw: Any) -> RetrievalContext:
        self.gathered.append(kw)
        if isinstance(self.context, Exception):
            raise self.context
        return self.context

    async def remember(self, **kw: Any) -> None:
        self.remembered.append(kw)


@pytest.fixture
def install(db_session_factory):
    async def seed(concepts: Sequence[str] = ("sliding-window",)) -> None:
        async with db_session_factory() as s:
            s.add(
                Problem(
                    slug=PAIR_PROBLEM["slug"],
                    title="t",
                    difficulty="Easy",
                    tags=[],
                    supported=False,
                )
            )
            await s.flush()
            s.add(ProblemSummary(slug=PAIR_PROBLEM["slug"], summary="s", concepts=list(concepts)))
            await s.commit()

    def put(retriever: FakeRetriever) -> FakeRetriever:
        app.dependency_overrides[get_retriever] = lambda: retriever
        return retriever

    yield put, seed
    app.dependency_overrides.pop(get_retriever, None)


@pytest.fixture
def use():
    from app.api.hint import get_generator
    from app.guard.llm_judge import get_judge

    def go(generator: ScriptedGenerator, judge: ScriptedJudge) -> None:
        app.dependency_overrides[get_generator] = lambda: generator
        app.dependency_overrides[get_judge] = lambda: judge

    yield go
    app.dependency_overrides.pop(get_generator, None)
    app.dependency_overrides.pop(get_judge, None)


def test_build_query_combines_concepts_failure_and_weak() -> None:
    q = build_query(["sliding-window"], "Crashes when the array is empty.", ["two-pointers"])
    assert q == "sliding window two pointers Crashes when the array is empty."
    assert build_query([], None, []) == ""
    assert build_query(["a-b"], None, ["a-b"]) == "a b"  # no duplicate words


def test_render_blocks_have_ids_and_empty_is_empty() -> None:
    ctx = RetrievalContext(NOTES, MISTAKES, ANALOGOUS)
    text = ctx.render()
    assert "<notes>" in text and "[note:sliding-window#Idea]" in text
    assert "<past_mistakes>" in text and "[mistake:7]" in text
    assert "<analogous_problems>" in text and "[problem:other-problem]" in text
    assert RetrievalContext().render() == ""
    assert [s.model_dump() for s in ctx.sources] == [
        {"type": "note", "slug": "sliding-window", "heading": "Idea"},
        {"type": "note", "slug": "two-pointers", "heading": "When it applies"},
    ]


async def test_notes_and_mistakes_reach_the_prompt_and_sources_the_done_event(
    client: AsyncClient, install, use
) -> None:
    put, seed = install
    await seed()
    retriever = put(FakeRetriever(RetrievalContext(NOTES, MISTAKES, [])))
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    events = await ask(client, level=2)
    user = gen.calls[0][1]["content"]
    assert "<notes>" in user and "sliding-window#Idea" in user and "<past_mistakes>" in user
    assert "background" in gen.calls[0][0]["content"].lower()  # the v3 prompt rules
    assert done(events)["sources"] == [
        {"type": "note", "slug": "sliding-window", "heading": "Idea"},
        {"type": "note", "slug": "two-pointers", "heading": "When it applies"},
    ]
    call = retriever.gathered[0]
    assert call["concepts"] == ("sliding-window",) and call["use_rag"] and call["use_memory"]
    assert shown(events) == CLEAN


async def test_level_4_gets_analogous_problems(client: AsyncClient, install, use) -> None:
    put, seed = install
    await seed()
    put(FakeRetriever(RetrievalContext([], [], ANALOGOUS)))
    gen = ScriptedGenerator(CLEAN)
    use(gen, ScriptedJudge(NONE))
    for level in (1, 2, 3):  # the ladder does not skip rungs
        await ask(client, level=level)
    gen.calls.clear()
    await ask(client, level=4)
    assert "<analogous_problems>" in gen.calls[0][1]["content"]
    assert "NEW small problem" in gen.calls[0][0]["content"]


async def test_quoting_a_note_is_blocked_and_sources_are_dropped(
    client: AsyncClient, install, use
) -> None:
    put, seed = install
    await seed()
    put(FakeRetriever(RetrievalContext(NOTES, [], [])))
    gen = ScriptedGenerator(NOTE_TEXT, NOTE_TEXT)  # both drafts quote the note
    use(gen, ScriptedJudge(NONE))
    events = await ask(client, level=2)
    assert len(gen.calls) == 2 and "quotes_source" in str(gen.calls[1])
    assert done(events)["sources"] == []  # the safe hint cites nothing


async def test_retrieval_failure_degrades_to_a_plain_hint(
    client: AsyncClient, install, use
) -> None:
    put, seed = install
    await seed()
    put(FakeRetriever(RuntimeError("db down")))
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    events = await ask(client, level=2)
    assert shown(events) == CLEAN and done(events)["sources"] == []


@pytest.mark.parametrize(
    ("env", "expect_rag", "expect_memory"), [("dev", True, True), ("eval", False, False)]
)
async def test_disable_flags_work_only_in_eval(
    client: AsyncClient,
    install,
    use,
    monkeypatch: pytest.MonkeyPatch,
    env,
    expect_rag,
    expect_memory,
) -> None:
    from app.config import reset_settings

    monkeypatch.setenv("APORIA_ENV", env)
    reset_settings()
    put, seed = install
    await seed()
    retriever = put(FakeRetriever(RetrievalContext()))
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    headers = {**HEADERS, "X-Aporia-Disable-RAG": "1", "X-Aporia-Disable-Memory": "1"}
    await ask(client, level=2, headers=headers)
    if not (expect_rag or expect_memory):
        assert retriever.gathered == []  # nothing to gather when both are switched off
        return
    call = retriever.gathered[0]
    assert (call["use_rag"], call["use_memory"]) == (expect_rag, expect_memory)


async def test_each_flag_is_independent_in_eval(
    client: AsyncClient, install, use, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import reset_settings

    monkeypatch.setenv("APORIA_ENV", "eval")
    reset_settings()
    put, seed = install
    await seed()
    retriever = put(FakeRetriever(RetrievalContext()))
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    await ask(client, level=2, headers={**HEADERS, "X-Aporia-Disable-RAG": "1"})
    call = retriever.gathered[0]
    assert (call["use_rag"], call["use_memory"]) == (False, True)


async def test_attempt_is_remembered_once_per_distinct_code(
    client: AsyncClient, install, use
) -> None:
    put, seed = install
    await seed()
    retriever = put(FakeRetriever(RetrievalContext()))
    use(ScriptedGenerator(CLEAN), ScriptedJudge(NONE))
    await ask(client, level=2, last_verdict="Wrong Answer")
    await ask(client, level=2, last_verdict="Wrong Answer")  # same code again
    assert [r["verdict"] for r in retriever.remembered] == ["Wrong Answer", None]
    await ask(
        client, level=2, last_verdict="Wrong Answer", code="def pairCount(a, t):\n    return 1"
    )
    assert retriever.remembered[-1]["verdict"] == "Wrong Answer"


def test_level_4_restating_the_problem_is_blocked() -> None:
    statement = "Count the pairs of indices whose values add up to exactly the target number given"
    draft = (
        "Here is a new problem. Count the pairs of indices whose values add up to exactly "
        "the target number given."
    )
    assert "restates_problem" in check_heuristics(draft, 4, statement=statement).reasons
    assert "restates_problem" not in check_heuristics(draft, 3, statement=statement).reasons
    fresh = "Imagine sorting socks by colour and counting matching pairs on a shelf."
    assert not check_heuristics(fresh, 4, statement=statement).blocked


def test_quoted_note_is_blocked_only_at_twelve_words() -> None:
    assert "quotes_source" in check_heuristics(NOTE_TEXT, 2, sources=[NOTE_TEXT]).reasons
    short = "Keep a summary of the current stretch and move the left"
    assert not check_heuristics(short, 2, sources=[NOTE_TEXT]).blocked


async def test_db_retriever_degrades_without_postgres_features(db_session_factory) -> None:
    """On SQLite the vector/full-text SQL cannot run; every part fails soft to an empty context."""
    from app.hints.retrieval_context import DbRetriever
    from app.rag.embedder import FakeEmbedder

    r = DbRetriever(db_session_factory, FakeEmbedder())
    ctx = await r.gather(
        level=4,
        slug="p",
        concepts=["sliding-window"],
        failure_text="Crashes.",
        device="d",
        use_rag=True,
        use_memory=True,
    )
    assert (ctx.notes, ctx.mistakes, ctx.analogous) == ([], [], [])
    await r.remember(
        device="d",
        slug="p",
        concepts=["sliding-window"],
        failure_text="Crashes when the array is empty.",
        verdict="Wrong Answer",
    )
