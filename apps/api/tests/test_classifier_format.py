from app.guard.classifier_format import (
    MIN_REFERENCE_TOKENS,
    SUMMARY_MAX_TOKENS,
    format_input,
    reference_text,
)


class WordTokenizer:
    """One token per whitespace-separated word (enough to test the budget logic)."""

    def encode(self, text: str) -> list[int]:
        return list(range(len(text.split())))

    def decode(self, ids: list[int]) -> str:  # not used for real text round-trips here
        raise NotImplementedError


class WordsKeep(WordTokenizer):
    """A tokenizer whose decode keeps the original words (set per call by `prime`)."""

    def __init__(self) -> None:
        self.words: dict[int, list[str]] = {}

    def encode(self, text: str) -> list[int]:
        words = text.split()
        key = hash(text)
        self.words[key] = words
        self._last = key
        return [key] * 0 + list(range(len(words)))

    def decode(self, ids: list[int]) -> str:
        return " ".join(self.words[self._last][: len(ids)])


def words(prefix: str, n: int) -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def count(text: str) -> int:
    return len(text.split())


def test_format_layout_for_short_inputs() -> None:
    tok = WordsKeep()
    out = format_input(2, "uses a window", "def f(): pass", "What if the list is empty?", tok)
    assert out == (
        "[LEVEL] 2 [PROBLEM] uses a window [REFERENCE] def f(): pass "
        "[REPLY] What if the list is empty?"
    )


def test_reference_is_truncated_first_and_reply_is_kept_whole() -> None:
    tok = WordsKeep()
    reply = words("r", 100)
    out = format_input(3, "s", words("ref", 1000), reply, tok, max_tokens=300)
    assert reply in out  # the reply survives intact
    assert "ref0" in out and "ref999" not in out  # only the start of the reference
    assert count(out) <= 300 - 2 + 6  # tags are single "words" here: allow the tag overhead


def test_reply_is_truncated_only_when_it_alone_does_not_fit() -> None:
    tok = WordsKeep()
    out = format_input(1, "s", words("ref", 500), words("r", 1000), tok, max_tokens=64)
    assert "r0" in out and "r999" not in out
    assert "ref0" not in out  # no room left for the reference
    assert out.endswith(words("r", 1000).split()[len(out.split("[REPLY] ")[1].split()) - 1])


def test_long_summary_is_capped() -> None:
    tok = WordsKeep()
    out = format_input(1, words("s", 500), "ref", "reply words here", tok, max_tokens=512)
    summary = out.split("[PROBLEM] ")[1].split(" [REFERENCE]")[0]
    assert count(summary) == SUMMARY_MAX_TOKENS


def test_tiny_reference_room_drops_the_reference() -> None:
    tok = WordsKeep()
    reply = words("r", 50)
    out = format_input(
        1, "s", words("ref", 100), reply, tok, max_tokens=2 + 5 + 1 + 50 + MIN_REFERENCE_TOKENS - 1
    )
    assert "[REFERENCE]  [REPLY]" in out and reply in out


def test_reference_text_keeps_the_solution_and_drops_scaffolding() -> None:
    module = (
        "import random\n\n"
        "def helper(x):\n    return x + 1\n\n"
        "def solve_optimal(a):\n    return helper(a)\n\n"
        "def solve_brute(a):\n    return a + 1\n\n"
        "def gen(rng, size):\n    return [1]\n\n"
        "def validate(args):\n    return True\n"
    )
    text = reference_text(module)
    assert "def solve_optimal" in text and "def helper" in text
    assert "solve_brute" not in text and "def gen" not in text and "validate" not in text
    assert "import random" not in text
    assert reference_text(None) == "" and reference_text("def (") == "def ("
