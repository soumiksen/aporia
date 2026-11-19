import pytest

from app.guard import heuristics as h
from app.guard.heuristics import check_heuristics
from app.guard.safe_hints import SAFE_HINTS
from tests.support.modules import GOOD_MODULE

REFERENCE = GOOD_MODULE

LEAKY_FULL = """Sure! Here is the solution:

```python
class Solution:
    def pairCount(self, nums, target):
        seen = {}
        count = 0
        for x in nums:
            count += seen.get(target - x, 0)
            seen[x] = seen.get(x, 0) + 1
        return count
```
"""

# Same algorithm, every identifier renamed and a comment added.
LEAKY_RENAMED = """```python
def f(a, t):
    # count the pairs
    m = {}
    c = 0
    for v in a:
        c += m.get(t - v, 0)
        m[v] = m.get(v, 0) + 1
    return c
```"""

LEAKY_UNFENCED = """Just write this:
def pairs(arr, goal):
    store = {}
    total = 0
    for item in arr:
        total += store.get(goal - item, 0)
        store[item] = store.get(item, 0) + 1
    return total
"""

# A fragment copied from the reference: the key loop body only.
LEAKY_FRAGMENT = """The key lines are:
```python
for x in nums:
    count += seen.get(target - x, 0)
    seen[x] = seen.get(x, 0) + 1
```"""

CLEAN_REPLIES = [
    "What happens in your code when the list has exactly two elements?",
    "Your approach is on the right track. Which inputs could make the inner loop run more times "
    "than you expect?",
    "Think about what information you could remember while scanning the list once. What would "
    "you need to know about the numbers you have already seen?",
    "Try this tiny example by hand:\n```\nnums = [1, 2]\ntarget = 3\n```\nWhat should the "
    "answer be, and what does your code return?",
    "```python\nx = 1\n```\nWhat does this snippet print? Compare with your code.",
]

ASSERTIONS = [
    "Yes, that's correct!",
    "Your solution is correct, nice work.",
    "Your code works for all inputs.",
    "Yep, your solution works.",
    "This is the right answer.",
    "You've got it, that passes everything.",
    "Your approach looks perfectly fine to submit.",
]


def reasons(draft: str, level: int = 2, ref: str | None = REFERENCE) -> list[str]:
    return check_heuristics(draft, level, ref).reasons


def test_clean_replies_pass_at_every_level() -> None:
    for level in (1, 2, 3, 4):
        for reply in CLEAN_REPLIES:
            result = check_heuristics(reply, level, REFERENCE)
            assert not result.blocked, (level, reply, result.reasons)


@pytest.mark.parametrize("level", [1, 2, 3])
def test_long_fenced_block_blocked_at_levels_1_to_3(level: int) -> None:
    draft = "```\n" + "\n".join(f"line {i}" for i in range(5)) + "\n```"
    assert "code_block_over_limit" in reasons(draft, level, None)


def test_three_line_block_allowed_and_level_4_allows_long_prose_blocks() -> None:
    three = "```\na\nb\nc\n```"
    assert not check_heuristics(three, 1, None).blocked
    long_block = "```\n" + "\n".join(f"step {i}" for i in range(6)) + "\n```"
    assert not check_heuristics(long_block, 4, None).blocked  # no reference, no similarity


@pytest.mark.parametrize("draft", [LEAKY_FULL, LEAKY_RENAMED, LEAKY_UNFENCED, LEAKY_FRAGMENT])
@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_reference_like_code_is_blocked_by_ast_similarity(draft: str, level: int) -> None:
    result = check_heuristics(draft, level, REFERENCE)
    assert result.blocked
    assert any(r.startswith("ast_similarity") for r in result.reasons), result.reasons
    assert result.similarity >= h.SIMILARITY_THRESHOLD


def test_similarity_ignores_names_comments_and_docstrings() -> None:
    a = h.ast_similarity(
        "def f(a, t):\n    '''doc'''\n    return a + t\n",
        h.reference_tokens("def solve_optimal(nums, target):\n    return nums + target\n"),
    )
    assert a >= 0.9  # wrapper tokens (Module) account for the small difference


def test_unrelated_code_has_low_similarity() -> None:
    other = """```python
def fib(n):
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a
```"""
    result = check_heuristics(other, 4, REFERENCE)
    assert not result.blocked and result.similarity < h.SIMILARITY_THRESHOLD


def test_non_python_fences_and_unparsable_code_do_not_crash() -> None:
    draft = "```java\nint x = 1;\nint y = 2;\nint z = 3;\n```\n```python\nthis is ( not code\n```"
    assert check_heuristics(draft, 4, REFERENCE).similarity == 0.0
    assert check_heuristics("anything", 2, "def (: broken reference").similarity == 0.0


@pytest.mark.parametrize("text", ASSERTIONS)
@pytest.mark.parametrize("level", [1, 2, 3])
def test_correctness_assertions_blocked_at_levels_1_to_3(text: str, level: int) -> None:
    assert "asserts_correctness" in reasons(text, level, None)


def test_correctness_assertions_not_checked_at_level_4() -> None:
    assert "asserts_correctness" not in reasons("Yes, that's correct!", 4, None)


def test_hedged_encouragement_is_not_an_assertion() -> None:
    for text in (
        "Your approach is on the right track. What about an empty list?",
        "Nice start! Which case might still break your code?",
        "I cannot say whether your code is correct. What do you expect on a tiny input?",
    ):
        assert not check_heuristics(text, 2, None).blocked, text


def test_every_safe_hint_template_passes_the_heuristics() -> None:
    for level, templates in SAFE_HINTS.items():
        for template in templates:
            result = check_heuristics(template, level, REFERENCE)
            assert not result.blocked, (level, template, result.reasons)
