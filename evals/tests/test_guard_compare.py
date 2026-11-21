import pytest

from guard_compare.metrics import TODO_TEXT, aggregate, render_markdown, render_table
from guard_compare.run import evaluate_mode, interpret


def rec(label, predicted, latency=10.0, cost=0.0, path="judge"):
    return {"label": label, "predicted": predicted, "latency_ms": latency,
            "cost_usd": cost, "path": path}  # fmt: skip


CANNED = [
    rec(1, 1, 10, 0.002, "judge"), rec(1, 1, 20, 0.0, "classifier_block"),
    rec(1, 0, 30, 0.0, "classifier_pass"), rec(1, 1, 40, 0.002, "judge"),
    rec(0, 0, 50, 0.0, "classifier_pass"), rec(0, 1, 60, 0.002, "judge"),
    rec(0, 0, 70, 0.0, "classifier_pass"), rec(0, 0, 80, 0.0, "classifier_pass"),
]  # fmt: skip


def test_aggregate_hand_computed() -> None:
    r = aggregate(CANNED)
    # 4 leaks: 3 caught -> recall 0.75. 4 safe: 1 blocked -> fpr 0.25. precision 3 / (3 + 1).
    assert (r["n"], r["n_leak"], r["n_safe"]) == (8, 4, 4)
    assert r["recall"] == 0.75 and r["false_positive_rate"] == 0.25 and r["precision"] == 0.75
    assert r["p50_ms"] == pytest.approx(45.0)  # median of 10..80 step 10
    assert r["p95_ms"] == pytest.approx(10 + 0.95 * 7 * 10)  # linear interpolation: 76.5
    assert r["cost_per_1000_usd"] == pytest.approx(0.006 / 8 * 1000)  # 3 judge calls at 0.002
    assert r["judge_share"] == pytest.approx(3 / 8)
    assert r["paths"] == {"judge": 3, "classifier_block": 1, "classifier_pass": 4}


def test_aggregate_handles_one_class_and_empty() -> None:
    only_safe = aggregate([rec(0, 0)])
    assert only_safe["recall"] is None and only_safe["false_positive_rate"] == 0.0
    assert only_safe["precision"] is None  # nothing was predicted positive
    empty = aggregate([])
    assert empty["n"] == 0 and empty["recall"] is None and empty["cost_per_1000_usd"] is None


async def test_evaluate_mode_times_each_item_and_keeps_labels() -> None:
    items = [{"label": 1, "id": "a"}, {"label": 0, "id": "b"}]

    async def decide(item, mode):
        return item["label"] == 1, "judge", 0.001

    out = await evaluate_mode("cascade", items, decide)
    assert [(o["label"], o["predicted"], o["cost_usd"]) for o in out] == [
        (1, 1, 0.001),
        (0, 0, 0.001),
    ]
    assert all(o["latency_ms"] >= 0 for o in out)


def table(**over):
    base = aggregate(CANNED)
    return {"prompted": {**base, **over}, "classifier_only": base, "cascade": base}


def test_render_and_interpretation_use_only_the_measured_numbers() -> None:
    sections = {"Held-out test split": table()}
    text = render_markdown(
        sections,
        meta={"Judge model": "`m`"},
        interpretation=interpret(sections),
        today="2026-01-01",
    )
    assert "| cascade | 8 (4 / 4) | 75.0% | 25.0% | 75.0% | 45 | 76 | $0.7500 | 37.5% |" in text
    assert "caught 75.0% of leaks" in text and "TODO" not in text
    assert any("| prompted |" in ln for ln in render_table("t", table()))


def test_todo_placeholder_is_clearly_marked_and_has_no_numbers() -> None:
    assert "TODO: no numbers yet" in TODO_TEXT and "%" not in TODO_TEXT.replace("%s", "")


def test_the_committed_guard_report_is_either_the_todo_or_real() -> None:
    from pathlib import Path

    text = (Path(__file__).resolve().parents[2] / "docs" / "results" / "guard.md").read_text()
    assert "TODO: no numbers yet" in text or "## Interpretation" in text
