"""End-to-end smoke test of the training code (needs torch and downloads the xsmall model).

Skipped unless APORIA_RUN_SMOKE=1 and torch is installed (the `ml/` uv environment):
    cd ml && APORIA_RUN_SMOKE=1 uv run pytest tests/test_smoke_train.py -q
"""

import json
import os

import pytest

pytest.importorskip("torch")
pytestmark = pytest.mark.skipif(not os.environ.get("APORIA_RUN_SMOKE"), reason="slow smoke run")


def test_smoke_training_writes_model_and_card(tmp_path) -> None:
    import sys

    from ml.train.train_classifier import main

    sys.argv = ["train", "--smoke", "--out", str(tmp_path)]
    assert main() == 0
    card = json.loads((tmp_path / "model_card.json").read_text())
    assert card["smoke"] is True and card["t_low"] <= card["t_high"]
    assert (tmp_path / "model").is_dir() and (tmp_path / "scores_test.json").exists()
