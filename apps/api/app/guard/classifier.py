"""The leak classifier: an int8 ONNX DeBERTa served on CPU with ONNX Runtime.

The model directory (APORIA_CLASSIFIER_DIR) holds `model.onnx`, `tokenizer.json` and
`model_card.json` (thresholds, max length). If it is missing or unusable the cascade falls back to
the prompted guard; that is logged once at WARNING. `onnxruntime` and `tokenizers` are imported
lazily (uv group `classifier`), so the API starts without them.
"""

import json
import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.guard.classifier_format import MAX_TOKENS, format_input, reference_text

logger = logging.getLogger("aporia.guard")

BATCH_SIZE = 16


class ClassifierError(RuntimeError):
    pass


class _TokenizerAdapter:
    """The formatter's view of a `tokenizers.Tokenizer` (no special tokens)."""

    def __init__(self, tokenizer: Any) -> None:
        self.tokenizer = tokenizer

    def encode(self, text: str) -> list[int]:
        return list(self.tokenizer.encode(text, add_special_tokens=False).ids)

    def decode(self, ids: list[int]) -> str:
        return str(self.tokenizer.decode(ids))


def _softmax_leak(row: Sequence[float]) -> float:
    import math

    m = max(row)
    exps = [math.exp(v - m) for v in row]
    return exps[1] / sum(exps)


class LeakClassifier:
    """P(leak) for formatted reply texts. Construct with a session and tokenizer to test."""

    def __init__(self, session: Any, tokenizer: Any, card: dict[str, Any], pad_id: int = 0) -> None:
        self.session = session
        self.tokenizer = tokenizer
        self.card = card
        self.pad_id = pad_id
        self.max_length = int(card.get("max_length", MAX_TOKENS))
        self.t_low = float(card["t_low"])
        self.t_high = float(card["t_high"])
        self.last_inference_ms = 0.0
        self._input_names = {i.name for i in session.get_inputs()}

    @classmethod
    def load(cls, directory: Path) -> "LeakClassifier":
        try:
            import onnxruntime as ort  # pyright: ignore[reportMissingImports]
            from tokenizers import Tokenizer  # pyright: ignore[reportMissingImports]

            card = json.loads((directory / "model_card.json").read_text())
            tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
            session = ort.InferenceSession(
                str(directory / "model.onnx"), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:  # noqa: BLE001 - any load problem means "no classifier"
            raise ClassifierError(f"cannot load classifier from {directory}: {exc}") from exc
        pad_id = tokenizer.token_to_id("[PAD]")
        return cls(session, tokenizer, card, 0 if pad_id is None else pad_id)

    def build_text(self, level: int, summary: str, reference_source: str | None, reply: str) -> str:
        """The input text, built exactly as training built it (shared formatter)."""
        return format_input(
            level,
            summary,
            reference_text(reference_source),
            reply,
            _TokenizerAdapter(self.tokenizer),
            self.max_length,
        )

    def _encode(self, texts: Sequence[str]) -> dict[str, Any]:
        import numpy as np

        self.tokenizer.enable_truncation(self.max_length)
        encodings = [self.tokenizer.encode(t) for t in texts]
        width = max(len(e.ids) for e in encodings)
        ids = np.full((len(encodings), width), self.pad_id, dtype="int64")
        mask = np.zeros((len(encodings), width), dtype="int64")
        for i, e in enumerate(encodings):
            ids[i, : len(e.ids)] = e.ids
            mask[i, : len(e.ids)] = 1
        feeds = {"input_ids": ids, "attention_mask": mask}
        return {k: v for k, v in feeds.items() if k in self._input_names}

    def predict_proba(self, texts: Sequence[str]) -> list[float]:
        """P(leak) per text, in batches of 16. Records the total inference time."""
        start = time.perf_counter()
        out: list[float] = []
        for i in range(0, len(texts), BATCH_SIZE):
            logits = self.session.run(None, self._encode(texts[i : i + BATCH_SIZE]))[0]
            out.extend(_softmax_leak(row) for row in logits)
        self.last_inference_ms = (time.perf_counter() - start) * 1000
        return out


_classifier: LeakClassifier | None = None
_loaded = False
_warned = False


def get_classifier() -> LeakClassifier | None:
    """Lazy singleton. None (logged once at WARNING) when APORIA_CLASSIFIER_DIR is unset or the
    artifacts cannot be loaded, in which case the guard falls back to the prompted mode."""
    global _classifier, _loaded, _warned
    if _loaded:
        return _classifier
    directory = get_settings().aporia_classifier_dir
    _loaded = True
    if not directory:
        return None
    try:
        _classifier = LeakClassifier.load(Path(directory))
    except ClassifierError as exc:
        if not _warned:
            logger.warning("leak classifier unavailable, using the prompted guard: %s", exc)
            _warned = True
    return _classifier


def reset_classifier() -> None:
    """Forget the cached classifier (tests, or after the artifacts change)."""
    global _classifier, _loaded, _warned
    _classifier, _loaded, _warned = None, False, False
