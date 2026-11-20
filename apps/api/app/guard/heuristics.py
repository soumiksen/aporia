"""Cheap, deterministic leak checks. Always run before the LLM judge."""

import ast
import builtins
import json
import re
import textwrap
from collections.abc import Iterator
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

SIMILARITY_THRESHOLD = 0.6  # block when AST similarity to the reference reaches this
MAX_CODE_LINES_LEVELS_1_3 = 3  # a fenced block longer than this is blocked at levels 1 to 3
MIN_SHINGLES_FOR_CONTAINMENT = 8
SHINGLE_SIZE = 4

FENCE_RE = re.compile(r"```[ \t]*([\w+#-]*)[^\n]*\n(.*?)```", re.DOTALL)
NON_PYTHON_FENCES = {
    "java", "javascript", "js", "ts", "typescript", "cpp", "c++", "c", "cs", "csharp", "go",
    "rust", "rs", "kotlin", "swift", "ruby", "php", "json", "yaml", "bash", "sh", "text", "txt",
}  # fmt: skip
CODEISH_LINE_RE = re.compile(
    r"^\s*(def |class |for .+:|while .+:|if .+:|elif .+:|else:|return\b|import |from \S+ import |"
    r"[A-Za-z_][\w.\[\], ]*\s*(=|\+=|-=)\s*\S)"
)

_ADV = r"(?:completely |totally |entirely |perfectly |absolutely )?"
CORRECTNESS_PATTERNS = [
    re.compile(
        r"\b(yes|yep|yeah|correct|right|exactly)\b[,!. ]+"
        r"(that'?s|that is|your|this|it|you)\b.{0,30}"
        r"\b(correct|right|works?|fine|good|solved)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\byour (solution|code|answer|approach|implementation|algorithm)\b.{0,25}"
        rf"\b(is|looks|seems|appears)\s+{_ADV}(correct|right|valid|good|fine|working)\b"
        r"(?!\s+(track|direction|idea|start))",
        re.IGNORECASE,
    ),
    re.compile(
        r"\byour (solution|code|answer|implementation)\b.{0,15}"
        r"\b(works|passes|will pass|should pass|is accepted|is optimal)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(that'?s|this is|it is|it's)\s+(the )?(correct|right)\s*(answer|solution|approach)?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\byou('ve| have)?\s+(got it|solved it|nailed it|found the bug)\b", re.IGNORECASE),
]

_BUILTINS = frozenset(dir(builtins))
_SKIP_NODES = (ast.Load, ast.Store, ast.Del)
_HELPER_EXCLUDED = {"gen", "validate", "solve_brute"}


@dataclass
class HeuristicResult:
    blocked: bool = False
    reasons: list[str] = field(default_factory=list)
    similarity: float = 0.0


# ---- code extraction ----


def fenced_blocks(text: str) -> list[tuple[str, str]]:
    """Returns (language, body) for each fenced block."""
    return [(m.group(1).lower(), m.group(2)) for m in FENCE_RE.finditer(text)]


def _count_code_lines(body: str) -> int:
    return sum(1 for line in body.splitlines() if line.strip())


def unfenced_code_runs(text: str) -> list[str]:
    """Runs of >= 2 consecutive code-looking lines outside fences (attacks that skip fences)."""
    stripped = FENCE_RE.sub("", text)
    runs: list[list[str]] = []
    current: list[str] = []
    for line in stripped.splitlines():
        if CODEISH_LINE_RE.match(line):
            current.append(line)
        elif current and not line.strip():
            continue  # blank lines do not end a run
        else:
            if len(current) >= 2:
                runs.append(current)
            current = []
    if len(current) >= 2:
        runs.append(current)
    return ["\n".join(r) for r in runs]


def python_candidates(text: str) -> list[str]:
    """Code snippets in the reply that might be Python."""
    out = [body for lang, body in fenced_blocks(text) if lang not in NON_PYTHON_FENCES]
    out.extend(unfenced_code_runs(text))
    return out


# ---- AST normalization and similarity ----


def _tokens(node: ast.AST) -> Iterator[str]:
    """Pre-order tokens of the tree with names, comments and constants normalized away."""
    if isinstance(node, _SKIP_NODES):
        return
    if isinstance(node, ast.Name):
        yield f"Name:{node.id}" if node.id in _BUILTINS else "Name"
        return
    if isinstance(node, ast.arg):
        yield "arg"
        return
    if isinstance(node, ast.Constant):
        yield f"Const:{type(node.value).__name__}"
        return
    yield type(node).__name__
    if isinstance(node, ast.Attribute):
        yield f"attr:{node.attr}"
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
        # the function name is normalized away; docstrings are dropped
        body = node.body
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            body = body[1:]
        for child in [*node.args.args, *node.args.kwonlyargs, *body]:
            yield from _tokens(child)
        return
    for child in ast.iter_child_nodes(node):
        yield from _tokens(child)


def _parse_snippet(code: str) -> ast.AST | None:
    code = textwrap.dedent(code)
    for candidate in (code, "def _wrapper_():\n" + textwrap.indent(code, "    ")):
        try:
            return ast.parse(candidate)
        except (SyntaxError, ValueError):
            continue
    return None


def normalized_tokens(code: str) -> list[str]:
    tree = _parse_snippet(code)
    return list(_tokens(tree)) if tree else []


def reference_tokens(module_source: str) -> list[str]:
    """Tokens of solve_optimal and its helper functions (not gen, validate or the brute force)."""
    try:
        tree = ast.parse(module_source)
    except (SyntaxError, ValueError):
        return []
    tokens: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name not in _HELPER_EXCLUDED:
            tokens.extend(_tokens(node))
    return tokens


def _shingles(tokens: list[str]) -> set[tuple[str, ...]]:
    return {tuple(tokens[i : i + SHINGLE_SIZE]) for i in range(len(tokens) - SHINGLE_SIZE + 1)}


def ast_similarity(code: str, reference: list[str]) -> float:
    """Similarity of a code snippet to the reference, in [0, 1].

    max(sequence ratio over node tokens, containment of the snippet's 4-token shingles in the
    reference). Containment catches partial leaks (a fragment copied from the reference); it only
    counts when the snippet has enough shingles to be meaningful.
    """
    tokens = normalized_tokens(code)
    if not tokens or not reference:
        return 0.0
    ratio = SequenceMatcher(None, tokens, reference, autojunk=False).ratio()
    snippet = _shingles(tokens)
    containment = 0.0
    if len(snippet) >= MIN_SHINGLES_FOR_CONTAINMENT:
        containment = len(snippet & _shingles(reference)) / len(snippet)
    return max(ratio, containment)


def max_similarity(text: str, reference_source: str | None) -> float:
    if not reference_source:
        return 0.0
    reference = reference_tokens(reference_source)
    return max((ast_similarity(c, reference) for c in python_candidates(text)), default=0.0)


# ---- expected-output reveal (execution-grounded hints) ----

EXPECTED_CUES = (
    r"expected|should (?:return|be|output|give|print|produce|equal|yield)|"
    r"correct (?:answer|output|result|value)|right answer|answer is|result is|output is|returns?"
)
MIN_STANDALONE_CHARS = 6
FILLER_WORDS = 3  # words allowed between a cue phrase and the value ("answer for this is 3")


def _norm(text: str) -> str:
    """Lowercase, single spaces, and no spaces around JSON punctuation ("[0, 1]" == "[0,1]")."""
    text = re.sub(r"\s+", " ", text.lower()).strip()
    text = re.sub(r"\s*([,:])\s*", r"\1", text)  # "a, b" and "a : b"
    text = re.sub(r"([\[{])\s+", r"\1", text)  # "[ 1" -> "[1" (not the space before "[")
    return re.sub(r"\s+([\]}])", r"\1", text)  # "1 ]" -> "1]"


def _spellings(value: Any) -> set[str]:
    """Spellings of a JSON value a reply might use: JSON, Python repr, unquoted string."""
    out = {_norm(json.dumps(value, separators=(",", ":"))), _norm(repr(value))}
    if isinstance(value, str):
        out.add(_norm(value))
    return {t for t in out if t}


def reveals_expected_output(
    draft: str, expected: Any, actual: Any = None, failing_input: Any = None
) -> bool:
    """True if the draft states the expected output of the failing input.

    Two rules on normalized text: (1) the expected value follows a cue such as "expected",
    "should return" or "the answer is" (up to three filler words in between); (2) a long, structured
    expected value (6+ characters, e.g. [[0,1],[2,3]]) appears anywhere, unless it is just a quote
    of the input. The student's own actual output is never treated as a reveal.
    """
    text = _norm(draft)
    actual_tokens = _spellings(actual) if actual is not None else set()
    input_text = _norm(json.dumps(failing_input)) if failing_input is not None else ""
    for token in _spellings(expected) - actual_tokens:
        cue = (
            rf"(?:{EXPECTED_CUES})(?: [a-z']+){{0,{FILLER_WORDS}}}"
            rf"[^a-z0-9\[\]{{}}\"']{{0,6}}[\"'`]?{re.escape(token)}(?![a-z0-9]|\.\d)"
        )
        if re.search(cue, text):
            return True
        if len(token) >= MIN_STANDALONE_CHARS and token in text and token not in input_text:
            return True
    return False


# ---- the combined check ----


HEDGE_RE = re.compile(
    r"(whether|\bif\b|\bcan'?t\b|\bcannot\b|\bcan not\b|\bwon'?t\b|\bnot\b|n't\b|"
    r"\bunable\b|\bunsure\b|\bwonder|\bhow to (tell|know)\b|\bask)[^.!?\n]*$",
    re.IGNORECASE,
)


def asserts_correctness(text: str) -> bool:
    """True if the reply asserts the student's code is correct. Hedged or negated mentions
    ("I cannot say whether your code is correct") are not assertions."""
    for pattern in CORRECTNESS_PATTERNS:
        for match in pattern.finditer(text):
            sentence_start = max(
                text.rfind(".", 0, match.start()), text.rfind("\n", 0, match.start())
            )
            if not HEDGE_RE.search(text[sentence_start + 1 : match.end()]):
                return True
    return False


def check_heuristics(
    draft: str,
    level: int,
    reference_source: str | None = None,
    failing_case: dict[str, Any] | None = None,
) -> HeuristicResult:
    result = HeuristicResult()

    if failing_case and reveals_expected_output(
        draft, failing_case.get("expected"), failing_case.get("actual"), failing_case.get("input")
    ):
        result.reasons.append("reveals_expected_output")

    if level <= 3:
        too_long = [
            body
            for _, body in fenced_blocks(draft)
            if _count_code_lines(body) > MAX_CODE_LINES_LEVELS_1_3
        ]
        too_long += [
            run for run in unfenced_code_runs(draft)
            if _count_code_lines(run) > MAX_CODE_LINES_LEVELS_1_3
        ]  # fmt: skip
        if too_long:
            result.reasons.append("code_block_over_limit")

        if asserts_correctness(draft):
            result.reasons.append("asserts_correctness")

    result.similarity = max_similarity(draft, reference_source)
    if result.similarity >= SIMILARITY_THRESHOLD:
        result.reasons.append(f"ast_similarity:{result.similarity:.2f}")

    result.blocked = bool(result.reasons)
    return result
