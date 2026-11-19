"""Synthetic reference modules and problem data used across tests (nothing from LeetCode)."""

import json
from typing import Any

PAIR_PROBLEM: dict[str, Any] = {
    "slug": "pair-count",
    "title": "Pair Count",
    "difficulty": "Easy",
    "tags": ["Array", "Hash Table"],
    "content_text": "Count index pairs i < j whose values add up to target.",
    "meta": {
        "name": "pairCount",
        "params": [{"name": "nums", "type": "integer[]"}, {"name": "target", "type": "integer"}],
        "return": {"type": "integer"},
    },
}

LINKED_PROBLEM: dict[str, Any] = {
    **PAIR_PROBLEM,
    "slug": "list-thing",
    "meta": {
        "name": "reverse",
        "params": [{"name": "head", "type": "ListNode"}],
        "return": {"type": "ListNode"},
    },
}

GEN_AND_VALIDATE = """
import random

def gen(rng, size):
    n = {"tiny": rng.randint(2, 4), "small": rng.randint(2, 12), "large": rng.randint(50, 200)}[size]
    return [[rng.randint(-5, 5) for _ in range(n)], rng.randint(-6, 6)]

def validate(args):
    nums, target = args
    return 2 <= len(nums) <= 1000 and all(-10**4 <= x <= 10**4 for x in nums)
"""

BRUTE = """
def solve_brute(nums, target):
    count = 0
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                count += 1
    return count
"""

GOOD_MODULE = (
    """
def solve_optimal(nums, target):
    seen = {}
    count = 0
    for x in nums:
        count += seen.get(target - x, 0)
        seen[x] = seen.get(x, 0) + 1
    return count
"""
    + BRUTE
    + GEN_AND_VALIDATE
)

# Wrong on duplicates: counts presence instead of multiplicity.
BUGGY_MODULE = (
    """
def solve_optimal(nums, target):
    seen = set()
    count = 0
    for x in nums:
        if target - x in seen:
            count += 1
        seen.add(x)
    return count
"""
    + BRUTE
    + GEN_AND_VALIDATE
)

# Returns a constant: fails the statement examples.
WRONG_EXAMPLES_MODULE = (
    """
def solve_optimal(nums, target):
    return 0
"""
    + BRUTE
    + GEN_AND_VALIDATE
)

MISSING_FUNCTION_MODULE = "def solve_optimal(nums, target):\n    return 0\n"

# Optimal correct, but gen produces too few valid cases (validate rejects most).
FEW_VALID_MODULE = GOOD_MODULE.replace("2 <= len(nums) <= 1000", "len(nums) == 7")

EXAMPLES_OK = [{"args": [[1, 2, 3, 4], 5], "expected": 2}]
EXAMPLES_DUPLICATES = [
    {"args": [[1, 2, 3, 4], 5], "expected": 2},
    {"args": [[2, 2, 2], 4], "expected": 3},
]


def analysis_reply(examples: list[dict[str, Any]] | None = None, comparison: str = "exact") -> str:
    return json.dumps(
        {
            "examples": examples if examples is not None else EXAMPLES_DUPLICATES,
            "method": "pairCount",
            "params": ["nums", "target"],
            "constraints": ["2 <= nums.length <= 1000"],
            "comparison": comparison,
        }
    )


def fenced(module: str) -> str:
    return f"Here is the module:\n```python\n{module}\n```"
