"""Aggregation for the guard comparison. Pure functions, tested with canned results."""

from collections import Counter
from collections.abc import Sequence
from typing import Any

from retrieval.metrics import percentile


def aggregate(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """One mode's row. Each record: {label, predicted, latency_ms, cost_usd, path}; label and
    predicted are 1 for leak. Recall is leaks caught; the false-positive rate is safe replies
    blocked; cost is USD per 1,000 checks."""
    tp = sum(1 for r in records if r["label"] == 1 and r["predicted"] == 1)
    fn = sum(1 for r in records if r["label"] == 1 and r["predicted"] == 0)
    fp = sum(1 for r in records if r["label"] == 0 and r["predicted"] == 1)
    tn = sum(1 for r in records if r["label"] == 0 and r["predicted"] == 0)
    n = len(records)
    latencies = [r["latency_ms"] for r in records]
    paths = Counter(r.get("path", "") for r in records)
    return {
        "n": n,
        "n_leak": tp + fn,
        "n_safe": fp + tn,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positive_rate": fp / (fp + tn) if fp + tn else None,
        "precision": tp / (tp + fp) if tp + fp else None,
        "p50_ms": percentile(latencies, 50) if latencies else None,
        "p95_ms": percentile(latencies, 95) if latencies else None,
        "cost_per_1000_usd": sum(r["cost_usd"] for r in records) / n * 1000 if n else None,
        "judge_share": paths.get("judge", 0) / n if n else None,
        "paths": dict(paths),
    }


def fmt(value: float | None, pct: bool = False, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1%}" if pct else f"{value:.{digits}f}"


def render_table(title: str, rows: dict[str, dict[str, Any]]) -> list[str]:
    lines = [
        f"### {title}",
        "",
        "| mode | n (leak / safe) | recall | false-positive rate | precision | p50 ms | p95 ms "
        "| cost per 1,000 checks | judge share |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for mode, r in rows.items():
        lines.append(
            f"| {mode} | {r['n']} ({r['n_leak']} / {r['n_safe']}) | {fmt(r['recall'], True)} "
            f"| {fmt(r['false_positive_rate'], True)} | {fmt(r['precision'], True)} "
            f"| {fmt(r['p50_ms'], digits=0)} | {fmt(r['p95_ms'], digits=0)} "
            f"| ${fmt(r['cost_per_1000_usd'], digits=4)} | {fmt(r['judge_share'], True)} |"
        )
    return [*lines, ""]


TODO_TEXT = """\
# Guard comparison: prompted vs classifier-only vs cascade

> **TODO: no numbers yet.** This file is filled in by `evals/guard_compare/run.py` once the leak
> classifier has been trained (`ml/modal_train.py`), exported (`ml/export/export_onnx.py`) and
> served from `APORIA_CLASSIFIER_DIR`. Nothing below is an estimate; until then there is no result
> to interpret.

How to produce it (after training):

```
cd apps/api
APORIA_CLASSIFIER_DIR=../../ml/artifacts/onnx \\
  uv run python ../../evals/guard_compare/run.py
```

It evaluates the three guard modes on (a) the held-out test split of
`ml/data/leak_dataset.jsonl` and (b) the replies from the Stage 2 red-team runs, and reports
recall, false-positive rate, precision, p50/p95 latency and the estimated cost per 1,000 checks.
"""


def render_markdown(
    sections: dict[str, dict[str, dict[str, Any]]],
    *,
    meta: dict[str, str],
    interpretation: str,
    today: str,
) -> str:
    lines = [
        "# Guard comparison: prompted vs classifier-only vs cascade",
        "",
        f"Generated {today} by `evals/guard_compare/run.py`.",
        "",
        *[f"- {k}: {v}" for k, v in meta.items()],
        "",
    ]
    for title, rows in sections.items():
        lines += render_table(title, rows)
    lines += [
        "Cost counts judge calls only (from LiteLLM's price table, so a local model costs $0); the "
        "classifier's cost is CPU time, which shows up in the latency columns, not in dollars. "
        "Heuristics run first in every mode.",
        "",
        "## Interpretation",
        "",
        interpretation.strip(),
        "",
    ]
    return "\n".join(lines)
