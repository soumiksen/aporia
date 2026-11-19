"""Deterministic fallback hints: generic Socratic prompts with no problem-specific content.

Used whenever the leak guard cannot approve a reply (leak twice, judge error, sandbox error).
Selection depends only on (slug, level), so the same problem and level always get the same hint.
"""

import hashlib

SAFE_HINTS: dict[int, tuple[str, ...]] = {
    1: (
        "What is the very first thing your code does with the input, and is that what you expect "
        "on the tiniest example you can think of?",
        "Try the smallest possible input by hand. What do you expect to happen, and what does "
        "your code actually do?",
        "Re-read the problem statement once more: which sentence describes the output, and does "
        "your code produce exactly that?",
        "Which part of your code runs once per element, and what could you do to avoid repeating "
        "work?",
    ),
    2: (
        "Think about an input at the edge of what the problem allows, such as a very short one or "
        "one where all values are equal. What does your code do there?",
        "Look for a place where your code does the same work more than once. Is there anything "
        "you could remember instead of recomputing?",
        "Compare the loop boundaries in your code with the ranges the problem describes. Could "
        "any loop run one step too many or too few?",
        "Pick two different small inputs and trace your code on both by hand. Where do your "
        "results first differ from what the statement says?",
    ),
    3: (
        "Break the problem into smaller steps in your own words. What must be known at each step, "
        "and what could you store so you never have to work it out twice?",
        "Solve a much smaller version of the problem by hand and write down every decision you "
        "make. Which of those decisions would repeat for larger inputs?",
        "What is the simplest correct solution, even if it is slow? Which of its steps repeat the "
        "same work, and how might you avoid that?",
    ),
    4: (
        "Consider a different task: finding the largest number in a list. You keep a best-so-far "
        "value, look at each number once, and update it when a better one appears. Could a "
        "running summary like that help with your problem?",
        "Consider a different task: counting the words in a sentence that start with a vowel. You "
        "walk through the words once, keep a counter, and update it when a condition holds. Could "
        "you describe your problem as a walk that updates something at each step?",
        "Picture checking whether a list is sorted: compare each neighbouring pair once and stop "
        "at the first pair that is out of order. What simple check could you apply at each step "
        "of your own problem?",
    ),
}


def safe_hint(slug: str, level: int) -> str:
    """Returns a deterministic generic hint for the level (clamped to 1..4)."""
    level = max(1, min(4, level))
    options = SAFE_HINTS[level]
    digest = hashlib.sha256(f"{slug}:{level}".encode()).digest()
    return options[int.from_bytes(digest[:4], "big") % len(options)]
