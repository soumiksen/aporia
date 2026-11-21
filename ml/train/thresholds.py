"""Cascade thresholds and the model card.

Below `t_low` a reply passes without the judge; above `t_high` it is blocked (and rewritten);
in between the LLM judge decides. Both are chosen on the validation set:

- t_low  = the highest threshold whose validation recall is still >= 0.99 (so at most about 1% of
  leaks are passed unseen).
- t_high = the lowest threshold whose validation precision is >= 0.95 (so blocks are rarely wrong).
- t_fpr5 = the threshold with the best validation recall at a false-positive rate <= 5%; it is the
  single operating point of the `classifier_only` guard mode.

If t_low would land at or above t_high (the classes separate so well that there is no
uncertain band), both are set to t_high: every reply is then decided by the classifier alone, and
both guarantees still hold.
"""

import datetime as dt
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ml.train.metrics import precision_recall_f1, recall_at_fpr

RECALL_FLOOR = 0.99
PRECISION_FLOOR = 0.95


def _candidates(scores: Sequence[float]) -> list[float]:
    return sorted(set(scores))


def choose_thresholds(
    y: Sequence[int],
    scores: Sequence[float],
    recall_floor: float = RECALL_FLOOR,
    precision_floor: float = PRECISION_FLOOR,
) -> dict[str, float | bool]:
    cands = _candidates(scores)
    # t_low: highest threshold with recall >= floor. If none (even the loosest misses too many)
    # nothing may pass unseen: t_low = 0.
    low_ok = [t for t in cands if precision_recall_f1(y, scores, t)["recall"] >= recall_floor]
    t_low = max(low_ok) if low_ok else 0.0
    # t_high: lowest threshold with precision >= floor. If none, the classifier never blocks alone.
    high_ok = [
        t for t in cands if precision_recall_f1(y, scores, t)["precision"] >= precision_floor
    ]
    t_high = min(high_ok) if high_ok else 1.0
    separable = t_low >= t_high
    if separable:
        t_low = t_high
    # classifier_only operating point: best validation recall at a false-positive rate <= 5%
    _, t_fpr5 = recall_at_fpr(y, scores)
    return {
        "t_low": float(t_low),
        "t_high": float(t_high),
        "t_fpr5": float(t_fpr5) if t_fpr5 != float("inf") else 1.0,
        "no_uncertain_band": separable,
    }


def routing_shares(scores: Sequence[float], t_low: float, t_high: float) -> dict[str, float]:
    """Share of replies that pass, are blocked, or go to the judge at these thresholds."""
    n = len(scores) or 1
    passed = sum(1 for s in scores if s < t_low)
    blocked = sum(1 for s in scores if s > t_high)
    return {"pass": passed / n, "block": blocked / n, "judge": (len(scores) - passed - blocked) / n}


def write_model_card(
    path: Path,
    *,
    thresholds: dict[str, Any],
    val_metrics: dict[str, float],
    test_metrics: dict[str, float],
    dataset_hash: str,
    base_model: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    card = {
        "base_model": base_model,
        "task": "binary classification: leak (1) vs safe (0)",
        "t_low": thresholds["t_low"],
        "t_high": thresholds["t_high"],
        "t_fpr5": thresholds.get("t_fpr5", thresholds["t_high"]),
        "no_uncertain_band": thresholds["no_uncertain_band"],
        "metrics": {"validation": val_metrics, "test": test_metrics},
        "dataset_hash": dataset_hash,
        "max_length": 512,
        "date": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        **(extra or {}),
    }
    path.write_text(json.dumps(card, indent=2) + "\n")
    return card
