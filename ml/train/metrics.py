"""Classification metrics for the leak classifier. Pure Python (no numpy), so they run anywhere.

Conventions: `y` holds 1 (leak) or 0 (safe); `scores` are P(leak); a prediction is positive when
score >= threshold. The primary metric is recall at a false-positive rate of at most 5%.
"""

from collections.abc import Sequence

FPR_BUDGET = 0.05


def _counts(
    y: Sequence[int], scores: Sequence[float], threshold: float
) -> tuple[int, int, int, int]:
    tp = fp = tn = fn = 0
    for label, score in zip(y, scores, strict=True):
        positive = score >= threshold
        if label == 1:
            tp, fn = tp + positive, fn + (not positive)
        else:
            fp, tn = fp + positive, tn + (not positive)
    return tp, fp, tn, fn


def confusion(y: Sequence[int], scores: Sequence[float], threshold: float) -> dict[str, int]:
    tp, fp, tn, fn = _counts(y, scores, threshold)
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def precision_recall_f1(
    y: Sequence[int], scores: Sequence[float], threshold: float
) -> dict[str, float]:
    tp, fp, _, fn = _counts(y, scores, threshold)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def false_positive_rate(y: Sequence[int], scores: Sequence[float], threshold: float) -> float:
    _, fp, tn, _ = _counts(y, scores, threshold)
    return fp / (fp + tn) if fp + tn else 0.0


def roc_points(y: Sequence[int], scores: Sequence[float]) -> list[tuple[float, float, float]]:
    """(threshold, fpr, tpr) from the strictest threshold (nothing positive) to the loosest.
    Tied scores move together, so the curve is exact."""
    pos = sum(y)
    neg = len(y) - pos
    order = sorted(zip(scores, y, strict=True), key=lambda p: -p[0])
    points = [(float("inf"), 0.0, 0.0)]
    tp = fp = 0
    i = 0
    while i < len(order):
        score = order[i][0]
        while i < len(order) and order[i][0] == score:
            tp, fp = tp + order[i][1], fp + (1 - order[i][1])
            i += 1
        points.append((score, fp / neg if neg else 0.0, tp / pos if pos else 0.0))
    return points


def roc_auc(y: Sequence[int], scores: Sequence[float]) -> float:
    """Area under the ROC curve (trapezoid rule). 0.5 if one class is missing."""
    if sum(y) in (0, len(y)):
        return 0.5
    pts = roc_points(y, scores)
    return sum((b[1] - a[1]) * (a[2] + b[2]) / 2 for a, b in zip(pts, pts[1:], strict=False))


def pr_auc(y: Sequence[int], scores: Sequence[float]) -> float:
    """Average precision: sum over thresholds of (recall step) x precision."""
    pos = sum(y)
    if pos == 0:
        return 0.0
    order = sorted(zip(scores, y, strict=True), key=lambda p: -p[0])
    tp = fp = 0
    area = 0.0
    prev_recall = 0.0
    i = 0
    while i < len(order):
        score = order[i][0]
        while i < len(order) and order[i][0] == score:
            tp, fp = tp + order[i][1], fp + (1 - order[i][1])
            i += 1
        recall = tp / pos
        area += (recall - prev_recall) * (tp / (tp + fp))
        prev_recall = recall
    return area


def recall_at_fpr(
    y: Sequence[int], scores: Sequence[float], max_fpr: float = FPR_BUDGET
) -> tuple[float, float]:
    """(recall, threshold): the best recall reachable while the false-positive rate stays at or
    below `max_fpr`, and the loosest threshold that achieves it."""
    best_recall, best_threshold = 0.0, float("inf")
    for threshold, fpr, tpr in roc_points(y, scores):
        if fpr <= max_fpr + 1e-12 and tpr >= best_recall:
            best_recall, best_threshold = tpr, threshold
    return best_recall, best_threshold


def summary(y: Sequence[int], scores: Sequence[float], threshold: float) -> dict[str, float]:
    """The reported metrics at one operating point, plus the threshold-free ones."""
    recall_fpr, _ = recall_at_fpr(y, scores)
    return {
        **precision_recall_f1(y, scores, threshold),
        "false_positive_rate": false_positive_rate(y, scores, threshold),
        "recall_at_fpr_5pct": recall_fpr,
        "roc_auc": roc_auc(y, scores),
        "pr_auc": pr_auc(y, scores),
        "n": float(len(y)),
    }
