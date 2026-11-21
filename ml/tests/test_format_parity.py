"""The API and the training code must build byte-identical classifier input."""

from types import SimpleNamespace

from app.guard.classifier import LeakClassifier
from app.guard.classifier_format import reference_text
from ml.train.data import format_records


class HFLike:
    """The `transformers` tokenizer surface the training formatter uses."""

    def encode(self, text, add_special_tokens=True):
        return [1 + sum(map(ord, w)) % 500 for w in text.split()]

    def decode(self, ids, skip_special_tokens=True):
        self.table = getattr(self, "table", {})
        return " ".join(self.table.get(i, f"w{i}") for i in ids)

    def __call__(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


class TokenizersLike:
    """`tokenizers.Tokenizer` surface, built to agree with HFLike."""

    def __init__(self, hf):
        self.hf = hf

    def encode(self, text, add_special_tokens=True):
        return SimpleNamespace(ids=self.hf.encode(text, add_special_tokens=False))

    def decode(self, ids):
        return self.hf.decode(ids)

    def enable_truncation(self, n):
        pass

    def token_to_id(self, token):
        return 0


class Session:
    def get_inputs(self):
        return [SimpleNamespace(name="input_ids")]


def test_api_and_training_format_identically_even_when_truncated() -> None:
    hf = HFLike()
    clf = LeakClassifier(
        Session(), TokenizersLike(hf), {"t_low": 0.1, "t_high": 0.9, "max_length": 128}
    )
    module = "def solve_optimal(a):\n    return sum(a)\n\ndef gen(r, s):\n    return []\n"
    problems = {"p": {"summary": "scan a list", "reference": module}}
    for reply in ("short reply?", "long " * 400):
        for level in (1, 4):
            rec = {"problem_slug": "p", "level": level, "reply": reply}
            training = format_records([rec], problems, hf, max_tokens=128)[0]
            serving = clf.build_text(level, "scan a list", module, reply)
            assert training == serving
    assert "gen(" not in serving and reference_text(module).startswith("def solve_optimal")
