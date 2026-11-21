"""The classifier's input text. Training (ml/) and the API both import this one function, so the
two can never drift apart (a parity test pins it).

    [LEVEL] {level} [PROBLEM] {concept summary} [REFERENCE] {reference, truncated} [REPLY] {reply}

Truncated to `max_tokens` tokens (including the two special tokens the model adds). The reply is
prioritized: the reference is truncated first, then the summary, and the reply only when it alone
does not fit.
"""

import ast
from typing import Protocol

MAX_TOKENS = 512
SPECIAL_TOKENS = 2  # [CLS] and [SEP]
SUMMARY_MAX_TOKENS = 80  # concept summaries are short; cap them so they never crowd out the reply
MIN_REFERENCE_TOKENS = 16  # below this the reference adds nothing; it is dropped


EXCLUDED_FUNCTIONS = {"gen", "validate", "solve_brute"}  # test scaffolding, not the solution


def reference_text(module_source: str | None) -> str:
    """The solution part of a reference module (solve_optimal and its helpers), as source text.
    Test scaffolding (generator, validator, brute force) and imports are left out so the token
    budget goes to the solution. Falls back to the whole source if it does not parse."""
    if not module_source:
        return ""
    try:
        tree = ast.parse(module_source)
    except (SyntaxError, ValueError):
        return module_source
    parts = [
        ast.get_source_segment(module_source, node) or ""
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.ClassDef) and node.name not in EXCLUDED_FUNCTIONS
    ]
    return "\n\n".join(p for p in parts if p)


class TokenCounter(Protocol):
    """The slice of a tokenizer the formatter needs (no special tokens added)."""

    def encode(self, text: str) -> list[int]: ...

    def decode(self, ids: list[int]) -> str: ...


def clip(tokenizer: TokenCounter, text: str, limit: int) -> str:
    """The first `limit` tokens of `text` (decoded back to text)."""
    if limit <= 0:
        return ""
    ids = tokenizer.encode(text)
    return text if len(ids) <= limit else tokenizer.decode(ids[:limit]).strip()


def format_input(
    level: int,
    summary: str,
    reference: str,
    reply: str,
    tokenizer: TokenCounter,
    max_tokens: int = MAX_TOKENS,
) -> str:
    budget = max_tokens - SPECIAL_TOKENS

    def n(text: str) -> int:
        return len(tokenizer.encode(text))

    head = f"[LEVEL] {int(level)} [PROBLEM] "
    summary = clip(tokenizer, summary.strip(), SUMMARY_MAX_TOKENS)
    mid_ref, mid_reply = " [REFERENCE] ", " [REPLY] "
    fixed = n(head) + n(mid_ref) + n(mid_reply)

    reply = reply.strip()
    # The reply gets whatever is left after the (capped) summary and the fixed tags, up to its own
    # length; the reference then takes what remains, and may end up empty.
    reply_budget = max(budget - fixed - n(summary), 0)
    reply = clip(tokenizer, reply, reply_budget)
    ref_budget = budget - fixed - n(summary) - n(reply)
    reference = (
        clip(tokenizer, reference.strip(), ref_budget) if ref_budget >= MIN_REFERENCE_TOKENS else ""
    )
    return f"{head}{summary}{mid_ref}{reference}{mid_reply}{reply}"
