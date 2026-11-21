import json
import logging
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from app.config import reset_settings
from app.guard import classifier as clf
from app.guard.classifier import ClassifierError, LeakClassifier, get_classifier, reset_classifier

CARD = {"t_low": 0.2, "t_high": 0.8, "max_length": 32}


class FakeTokenizer:
    """One token per word; ids are a stable hash of the word."""

    def __init__(self) -> None:
        self.truncation: int | None = None

    def enable_truncation(self, n: int) -> None:
        self.truncation = n

    def _ids(self, text: str) -> list[int]:
        return [1 + sum(map(ord, w)) % 50 for w in text.split()]

    def encode(self, text: str, add_special_tokens: bool = True):
        ids = self._ids(text)
        if add_special_tokens:
            ids = [101, *ids[: (self.truncation or 10**9) - 2], 102]
        return SimpleNamespace(ids=ids)

    def decode(self, ids: list[int]) -> str:
        return " ".join(f"w{i}" for i in ids)

    def token_to_id(self, token: str) -> int | None:
        return 0 if token == "[PAD]" else None


class FakeSession:
    """Logit for 'leak' grows with the number of non-pad tokens whose id is above 25."""

    def __init__(self, names=("input_ids", "attention_mask")) -> None:
        self.names = names
        self.calls: list[dict[str, np.ndarray]] = []

    def get_inputs(self):
        return [SimpleNamespace(name=n) for n in self.names]

    def run(self, _outputs, feeds):
        self.calls.append(feeds)
        ids = feeds["input_ids"]
        mask = feeds.get("attention_mask", np.ones_like(ids))
        score = ((ids > 25) & (mask == 1)).sum(axis=1).astype("float32")
        return [np.stack([np.zeros_like(score), score - 2.0], axis=1)]


def make(names=("input_ids", "attention_mask")) -> tuple[LeakClassifier, FakeSession]:
    session = FakeSession(names)
    return LeakClassifier(session, FakeTokenizer(), CARD, pad_id=0), session


def test_predict_proba_returns_probabilities_in_order() -> None:
    c, _ = make()
    probs = c.predict_proba(["a b c", "zzzz zzzz zzzz zzzz", ""])
    assert len(probs) == 3 and all(0.0 <= p <= 1.0 for p in probs)
    assert probs[1] > probs[0]  # more high ids -> higher leak logit
    assert c.last_inference_ms >= 0


def test_batching_pads_and_masks_and_matches_single_calls() -> None:
    c, session = make()
    texts = [f"word{i} " * (i + 1) for i in range(40)]
    batch = c.predict_proba(texts)
    assert [len(call["input_ids"]) for call in session.calls] == [16, 16, 8]  # batches of 16
    first = session.calls[0]
    assert first["input_ids"].shape == first["attention_mask"].shape
    assert (first["input_ids"][first["attention_mask"] == 0] == 0).all()  # padding uses pad id
    singles = [c.predict_proba([t])[0] for t in texts]
    assert batch == pytest.approx(singles)  # padding does not change the result


def test_only_inputs_the_model_declares_are_fed() -> None:
    c, session = make(names=("input_ids",))
    c.predict_proba(["a b"])
    assert set(session.calls[0]) == {"input_ids"}


def test_inputs_are_truncated_to_max_length() -> None:
    c, session = make()
    c.predict_proba(["tok " * 500])
    assert session.calls[0]["input_ids"].shape[1] <= CARD["max_length"]


def test_thresholds_and_build_text_use_the_card_and_shared_formatter() -> None:
    c, _ = make()
    assert (c.t_low, c.t_high, c.max_length) == (0.2, 0.8, 32)
    text = c.build_text(2, "a window", "def solve_optimal(a):\n    return a\n", "ask me")
    assert text.startswith("[LEVEL] 2 [PROBLEM] a window [REFERENCE] ")
    assert text.endswith("[REPLY] ask me")


def test_load_from_a_directory_needs_all_artifacts(tmp_path: Path) -> None:
    with pytest.raises(ClassifierError):
        LeakClassifier.load(tmp_path)  # nothing there
    (tmp_path / "model_card.json").write_text(json.dumps(CARD))
    with pytest.raises(ClassifierError):
        LeakClassifier.load(tmp_path)  # still no model or tokenizer


def test_missing_directory_falls_back_and_warns_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    reset_classifier()
    monkeypatch.setenv("APORIA_CLASSIFIER_DIR", str(tmp_path / "nope"))
    reset_settings()
    with caplog.at_level(logging.WARNING, logger="aporia.guard"):
        assert get_classifier() is None
        assert get_classifier() is None
    warnings = [r for r in caplog.records if "classifier unavailable" in r.message]
    assert len(warnings) == 1
    reset_classifier()


def test_unset_directory_means_no_classifier_without_noise(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    reset_classifier()
    monkeypatch.delenv("APORIA_CLASSIFIER_DIR", raising=False)
    reset_settings()
    with caplog.at_level(logging.WARNING, logger="aporia.guard"):
        assert get_classifier() is None
    assert not caplog.records
    reset_classifier()


def test_singleton_is_loaded_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reset_classifier()
    made = []

    def fake_load(directory):
        made.append(directory)
        return make()[0]

    monkeypatch.setattr(clf.LeakClassifier, "load", staticmethod(fake_load))
    monkeypatch.setenv("APORIA_CLASSIFIER_DIR", str(tmp_path))
    reset_settings()
    assert get_classifier() is get_classifier() and len(made) == 1
    reset_classifier()


SMOKE_DIR = Path(__file__).resolve().parents[3] / "ml" / "artifacts" / "smoke" / "onnx"


@pytest.mark.skipif(not (SMOKE_DIR / "model.onnx").exists(), reason="no exported smoke model")
def test_real_exported_model_loads_and_predicts() -> None:
    pytest.importorskip("onnxruntime")
    c = LeakClassifier.load(SMOKE_DIR)
    texts = [
        c.build_text(1, "s", "def solve_optimal(a):\n    return a", r) for r in ("a?", "b" * 400)
    ]
    probs = c.predict_proba(texts)
    assert len(probs) == 2 and all(0 <= p <= 1 for p in probs)
    # dynamic int8 quantization scales activations per batch, so padding moves p by a little
    assert c.predict_proba(texts[:1])[0] == pytest.approx(probs[0], abs=0.02)
