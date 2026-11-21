"""Small text helpers shared by the RAG pipeline and the leak guard."""

import re
from collections.abc import Iterable


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def shares_run(a: str, b: str, run: int) -> bool:
    """True if the two texts share `run` or more consecutive words."""
    wa, wb = words(a), words(b)
    if len(wa) < run or len(wb) < run:
        return False
    grams = {tuple(wb[i : i + run]) for i in range(len(wb) - run + 1)}
    return any(tuple(wa[i : i + run]) in grams for i in range(len(wa) - run + 1))


def shares_run_with_any(text: str, others: Iterable[str], run: int) -> bool:
    return any(shares_run(text, o, run) for o in others)
