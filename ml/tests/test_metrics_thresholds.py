import json

import pytest
from ml.train.metrics import (
    confusion,
    false_positive_rate,
    pr_auc,
    precision_recall_f1,
    recall_at_fpr,
    roc_auc,
    roc_points,
    summary,
)
from ml.train.thresholds import choose_thresholds, routing_shares, write_model_card

# Hand-made: scores for 4 positives and 4 negatives.
Y = [1, 1, 1, 1, 0, 0, 0, 0]
S = [0.9, 0.8, 0.7, 0.4, 0.6, 0.3, 0.2, 0.1]


def test_confusion_and_prf_at_a_threshold() -> None:
    # threshold 0.5: predicted positive = 0.9, 0.8, 0.7, 0.6 -> tp 3, fp 1, fn 1, tn 3
    assert confusion(Y, S, 0.5) == {"tp": 3, "fp": 1, "tn": 3, "fn": 1}
    m = precision_recall_f1(Y, S, 0.5)
    assert m == pytest.approx({"precision": 0.75, "recall": 0.75, "f1": 0.75})
    assert false_positive_rate(Y, S, 0.5) == pytest.approx(0.25)
    assert precision_recall_f1(Y, S, 2.0) == {"precision": 0.0, "recall": 0.0, "f1": 0.0}


def test_roc_auc_hand_computed() -> None:
    # 16 (pos, neg) pairs; the positive scores higher in 15 of them (0.4 loses only to 0.6).
    assert roc_auc(Y, S) == pytest.approx(15 / 16)
    assert roc_auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert roc_auc([1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]) == 0.0
    assert roc_auc([1, 0], [0.5, 0.5]) == pytest.approx(0.5)  # a tie is half a win
    assert roc_auc([1, 1], [0.3, 0.4]) == 0.5  # one class only


def test_pr_auc_hand_computed() -> None:
    # Ranked: P P P N P N N N. Precision at each recall step: 1, 1, 1, 4/5 (the last positive).
    # Average precision = (1 + 1 + 1 + 0.8) / 4 = 0.95.
    assert pr_auc(Y, S) == pytest.approx(0.95)
    assert pr_auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == 1.0
    assert pr_auc([0, 0], [0.1, 0.2]) == 0.0


def test_recall_at_fpr_hand_computed() -> None:
    # Allowing no false positives (fpr <= 0): the best threshold is 0.7 (recall 3/4).
    recall, threshold = recall_at_fpr(Y, S, 0.0)
    assert (recall, threshold) == (0.75, 0.7)
    # fpr <= 25% allows one negative: threshold 0.4 catches all positives with 1 false positive.
    recall, threshold = recall_at_fpr(Y, S, 0.25)
    assert (recall, threshold) == (1.0, 0.4)
    # The default budget (5%) of 4 negatives allows none.
    assert recall_at_fpr(Y, S)[0] == 0.75


def test_roc_points_group_ties() -> None:
    pts = roc_points([1, 0, 1, 0], [0.5, 0.5, 0.5, 0.1])
    assert pts[1] == (0.5, 0.5, 1.0)  # all three tied items move together
    assert pts[-1][1:] == (1.0, 1.0)


def test_summary_has_every_reported_metric() -> None:
    m = summary(Y, S, 0.5)
    assert set(m) >= {
        "precision",
        "recall",
        "f1",
        "false_positive_rate",
        "recall_at_fpr_5pct",
        "roc_auc",
        "pr_auc",
        "n",
    }
    assert m["n"] == 8 and m["roc_auc"] == pytest.approx(15 / 16)


def test_thresholds_from_a_validation_set() -> None:
    y = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    s = [
        0.95,
        0.9,
        0.85,
        0.8,
        0.75,
        0.7,
        0.65,
        0.6,
        0.5,
        0.35,  # positives
        0.55,
        0.3,
        0.25,
        0.2,
        0.15,
        0.1,
        0.08,
        0.05,
        0.03,
        0.01,
    ]  # negatives
    t = choose_thresholds(y, s, recall_floor=0.99, precision_floor=0.95)
    # recall >= 0.99 needs all 10 positives: the highest such threshold is the lowest positive 0.35
    assert t["t_low"] == 0.35
    # precision >= 0.95: at 0.6 the 8 positives >= 0.6 have no negative above them (1.0); below
    # it the negative at 0.55 drops precision to 8/9, 9/10 and 10/11, all under 0.95.
    assert t["t_high"] == 0.6
    assert not t["no_uncertain_band"]
    shares = routing_shares(s, t["t_low"], t["t_high"])
    assert shares["pass"] + shares["block"] + shares["judge"] == pytest.approx(1.0)
    assert shares["pass"] == pytest.approx(9 / 20)  # the 9 negatives scoring below 0.35


def test_thresholds_when_classes_separate_perfectly() -> None:
    t = choose_thresholds([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1])
    assert t["no_uncertain_band"] and t["t_low"] == t["t_high"] == 0.8


def test_thresholds_fail_safe_when_the_floors_are_unreachable() -> None:
    # a useless classifier: no threshold gets 99% recall except 0 -> nothing passes unseen
    t = choose_thresholds([1, 0, 1, 0], [0.1, 0.9, 0.2, 0.8])
    assert t["t_low"] <= t["t_high"]


def test_model_card_round_trip(tmp_path) -> None:
    card = write_model_card(
        tmp_path / "model_card.json",
        thresholds={"t_low": 0.1, "t_high": 0.9, "no_uncertain_band": False},
        val_metrics={"f1": 0.9},
        test_metrics={"f1": 0.8},
        dataset_hash="abc",
        base_model="m",
    )
    loaded = json.loads((tmp_path / "model_card.json").read_text())
    assert loaded == card and loaded["t_low"] == 0.1 and loaded["dataset_hash"] == "abc"
    assert loaded["metrics"]["test"] == {"f1": 0.8}
