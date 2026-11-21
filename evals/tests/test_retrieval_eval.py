import math

import pytest

from retrieval.metrics import (
    dedupe,
    mean,
    percentile,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    summarize,
)
from retrieval.run import LABELED, MODES, Pair, evaluate, load_pairs, render_markdown

RANKING = ["a", "b", "c", "d", "e"]


def test_precision_at_k_hand_computed() -> None:
    relevant = {"b", "e"}
    assert precision_at_k(RANKING, relevant, 3) == pytest.approx(1 / 3)
    assert precision_at_k(RANKING, relevant, 5) == pytest.approx(2 / 5)
    assert precision_at_k(RANKING, relevant, 1) == 0.0
    assert precision_at_k(["b"], {"b"}, 3) == pytest.approx(1 / 3)  # short list: k is the divisor


def test_recall_at_k_hand_computed() -> None:
    assert recall_at_k(RANKING, {"b", "e"}, 3) == pytest.approx(1 / 2)
    assert recall_at_k(RANKING, {"b", "e"}, 5) == 1.0
    assert recall_at_k(RANKING, {"z"}, 5) == 0.0
    assert recall_at_k(RANKING, set(), 5) == 0.0


def test_reciprocal_rank_hand_computed() -> None:
    assert reciprocal_rank(RANKING, {"b", "e"}) == pytest.approx(1 / 2)
    assert reciprocal_rank(RANKING, {"c"}) == pytest.approx(1 / 3)
    assert reciprocal_rank(RANKING, {"a"}) == 1.0
    assert reciprocal_rank(RANKING, {"z"}) == 0.0


def test_dedupe_percentile_mean() -> None:
    assert dedupe(["a", "b", "a", "c", "b"]) == ["a", "b", "c"]
    assert percentile([10, 20, 30, 40], 50) == pytest.approx(25.0)
    assert percentile([10, 20, 30, 40], 95) == pytest.approx(38.5)
    assert percentile([7], 95) == 7 and math.isnan(percentile([], 50))
    assert mean([1, 2, 3]) == 2 and math.isnan(mean([]))


def test_summarize_over_two_queries() -> None:
    s = summarize([["a", "b", "c"], ["x", "y", "z"]], [{"a"}, {"z"}], [10.0, 30.0])
    assert s["p@3"] == pytest.approx((1 / 3 + 1 / 3) / 2)
    assert s["mrr"] == pytest.approx((1 + 1 / 3) / 2)
    assert s["r@5"] == 1.0 and s["p50_ms"] == pytest.approx(20.0) and s["n"] == 2


async def test_evaluate_and_render() -> None:
    pairs = [
        Pair("q1", "x", frozenset({"a"}), "needs_human_label"),
        Pair("q2", "y", frozenset({"b"}), LABELED),
    ]

    async def search(query: str, mode: str) -> list[str]:
        return ["a", "a", "b"] if query == "x" else ["c", "b"]

    results = await evaluate(pairs, search, ["vector", "fts"])
    assert results["vector"]["mrr"] == pytest.approx((1 + 1 / 2) / 2)  # duplicates collapse
    text = render_markdown(
        results,
        pairs,
        embedder="fake-embedder",
        skipped={"hybrid_rerank": "disabled"},
        today="2026-01-01",
    )
    assert "Provisional" in text and "1 human-labeled" in text
    assert "| vector |" in text and "`hybrid_rerank` skipped" in text
    final = render_markdown(
        results,
        [Pair("q", "x", frozenset({"a"}), LABELED)],
        embedder="m",
        skipped={},
        today="2026-01-01",
    )
    assert "Provisional" not in final


def test_pairs_file_is_well_formed() -> None:
    from app.rag.taxonomy import load_taxonomy

    pairs = load_pairs()
    taxonomy = load_taxonomy()
    assert 90 <= len(pairs) <= 130
    assert len({p.query_id for p in pairs}) == len(pairs)
    assert all(p.relevant and all(s in taxonomy for s in p.relevant) for p in pairs)
    assert all(p.status == "needs_human_label" for p in pairs)  # until the user reviews them
    assert set(MODES) == {"vector", "fts", "hybrid", "hybrid_rerank"}


# ---- hint-quality comparison (offline: scripted API and judge) ----


async def test_hint_quality_pipeline_offline() -> None:
    from redteam.loaders import load_problems
    from retrieval import hint_quality as hq

    cases = hq.build_cases()
    assert len(cases) == 30 and {c["level"] for c in cases} == {1, 2, 3}
    assert set(hq.PROBLEM_CONCEPTS) <= set(load_problems())
    seen: list[tuple[bool, bool]] = []

    async def call_api(body, device, rag_off, memory_off):
        seen.append((rag_off, memory_off))
        rag = not rag_off
        return {"text": "What happens on an empty list?", "sources": [{"slug": "x"}] if rag else []}

    async def judge(messages):
        return '{"correctness": 4, "socratic": 5, "specificity": 3, "no_leakage": 5}'

    records = await hq.run_quality(cases[:3], load_problems(), call_api, judge, run_id="t")
    assert len(records) == 3 * 4 and set(seen) == {
        (True, True),
        (False, True),
        (True, False),
        (False, False),
    }
    table = hq.aggregate(records)
    assert (
        table["RAG + memory"]["with_sources"] == 3
        and table["baseline (RAG off, memory off)"]["with_sources"] == 0
    )
    assert table["RAG only"]["socratic"] == 5 and table["RAG only"]["scored"] == 3
    text = hq.render_markdown(
        table, models={"fast": "m", "judge": "j"}, n_cases=3, today="2026-01-01"
    )
    assert "| RAG + memory |" in text and "Change from baseline" in text


def test_rubric_parsing() -> None:
    from retrieval.hint_quality import parse_rubric

    good = 'Sure: {"correctness": 4, "socratic": 3, "specificity": 2, "no_leakage": 5}'
    assert parse_rubric(good) == {
        "correctness": 4,
        "socratic": 3,
        "specificity": 2,
        "no_leakage": 5,
    }
    assert parse_rubric("not json") is None
    assert (
        parse_rubric('{"correctness": 9, "socratic": 3, "specificity": 2, "no_leakage": 5}') is None
    )
    assert parse_rubric('{"correctness": 4}') is None


async def test_judge_failure_is_unscored_not_fatal() -> None:
    from retrieval.hint_quality import score_reply

    async def boom(messages):
        raise RuntimeError("down")

    assert await score_reply(boom, "s", "c", 1, "r") is None
