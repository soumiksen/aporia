"""Ranking metrics for the retrieval eval. Pure functions, unit-tested by hand-computed cases."""

import math
from collections.abc import Sequence


def dedupe(ranking: Sequence[str]) -> list[str]:
    """Keeps the first occurrence of each item (several note chunks can share a concept)."""
    return list(dict.fromkeys(ranking))


def precision_at_k(ranking: Sequence[str], relevant: set[str], k: int) -> float:
    """Relevant items in the top k, divided by k (k stays the denominator for short lists)."""
    return sum(1 for r in ranking[:k] if r in relevant) / k


def recall_at_k(ranking: Sequence[str], relevant: set[str], k: int) -> float:
    if not relevant:
        return 0.0
    return len(relevant & set(ranking[:k])) / len(relevant)


def reciprocal_rank(ranking: Sequence[str], relevant: set[str]) -> float:
    for rank, item in enumerate(ranking, start=1):
        if item in relevant:
            return 1.0 / rank
    return 0.0


def percentile(values: Sequence[float], p: float) -> float:
    """Linear-interpolation percentile (p in 0..100), as numpy's default."""
    if not values:
        return math.nan
    ordered = sorted(values)
    pos = (len(ordered) - 1) * p / 100
    lo, hi = math.floor(pos), math.ceil(pos)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (pos - lo)


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else math.nan


def summarize(
    rankings: Sequence[Sequence[str]], relevants: Sequence[set[str]], latencies_ms: Sequence[float]
) -> dict[str, float]:
    """One row of the results table, over all queries."""
    return {
        "p@3": mean(
            [precision_at_k(r, rel, 3) for r, rel in zip(rankings, relevants, strict=True)]
        ),
        "p@5": mean(
            [precision_at_k(r, rel, 5) for r, rel in zip(rankings, relevants, strict=True)]
        ),
        "r@5": mean([recall_at_k(r, rel, 5) for r, rel in zip(rankings, relevants, strict=True)]),
        "mrr": mean([reciprocal_rank(r, rel) for r, rel in zip(rankings, relevants, strict=True)]),
        "p50_ms": percentile(latencies_ms, 50),
        "p95_ms": percentile(latencies_ms, 95),
        "n": float(len(rankings)),
    }
