"""Generates original synthetic practice problems (no scraped content) with the LLM.

Problems are validated against a schema, deduplicated by title and by embedding similarity of the
statement, and written to `ml/data/problems/<slug>.json`. Verification of the reference solutions
is a separate step (`build_references.py`).

Costs LLM calls. A cost estimate is printed first. Run at full size yourself:
    uv --directory apps/api run python ../../ml/data/synth_problems.py --count 150
Quick check with a few problems:
    uv --directory apps/api run python ../../ml/data/synth_problems.py --limit 3
"""

import argparse
import asyncio
import json
import math
import re
import sys
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pydantic import BaseModel, Field, field_validator  # noqa: E402

from ml.common import load_ml_prompt, render  # noqa: E402

PROBLEMS_DIR = Path(__file__).resolve().parent / "problems"
CATEGORIES = [
    "arrays", "strings", "hashing", "two pointers", "sliding windows", "binary search",
    "stacks", "intervals", "simple dynamic programming", "greedy",
]  # fmt: skip
DIFFICULTIES = ["Easy", "Easy", "Medium"]
ALLOWED_TYPES = {
    "integer", "long", "double", "boolean", "string",
    "integer[]", "string[]", "boolean[]", "integer[][]",
}  # fmt: skip
SIMILARITY_THRESHOLD = 0.9  # reject a problem whose statement is this similar to an accepted one
MAX_ATTEMPTS_PER_PROBLEM = 3
# Rough planning numbers for the cost estimate (tokens per generation call).
EST_INPUT_TOKENS = 700
EST_OUTPUT_TOKENS = 500

LLM = Callable[[list[dict[str, str]]], Awaitable[str]]


class Param(BaseModel):
    name: str = Field(pattern=r"^[a-z][A-Za-z0-9_]*$")
    type: str

    @field_validator("type")
    @classmethod
    def known_type(cls, v: str) -> str:
        if v not in ALLOWED_TYPES:
            raise ValueError(f"type {v!r} is not allowed")
        return v


class Example(BaseModel):
    args: list[Any]
    expected: Any


class SynthProblem(BaseModel):
    slug: str = Field(pattern=r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", max_length=60)
    title: str = Field(min_length=3, max_length=80)
    statement: str = Field(min_length=40, max_length=1500)
    method: str = Field(pattern=r"^[a-z][A-Za-z0-9]*$")
    params: list[Param] = Field(min_length=1, max_length=4)
    return_type: str
    constraints: list[str] = Field(default_factory=list, max_length=8)
    examples: list[Example] = Field(min_length=2, max_length=4)
    comparison: Literal["exact", "unordered"] = "exact"
    category: str = ""
    difficulty: str = "Easy"

    @field_validator("return_type")
    @classmethod
    def known_return(cls, v: str) -> str:
        if v not in ALLOWED_TYPES:
            raise ValueError(f"return type {v!r} is not allowed")
        return v

    def check_examples(self) -> None:
        n = len(self.params)
        for ex in self.examples:
            if len(ex.args) != n:
                raise ValueError(f"an example has {len(ex.args)} args but there are {n} params")

    def to_pipeline_problem(self) -> dict[str, Any]:
        """The dict `build_reference` takes. The examples are appended to the statement because
        the pipeline only trusts examples that appear in it."""
        lines = [self.statement.strip(), ""]
        if self.constraints:
            lines += ["Constraints:", *[f"- {c}" for c in self.constraints], ""]
        for i, ex in enumerate(self.examples, 1):
            lines.append(
                f"Example {i}: input {json.dumps(ex.args)} gives {json.dumps(ex.expected)}."
            )
        return {
            "slug": self.slug,
            "title": self.title,
            "difficulty": self.difficulty,
            "tags": [self.category] if self.category else [],
            "content_text": "\n".join(lines),
            "meta": {
                "name": self.method,
                "params": [p.model_dump() for p in self.params],
                "return": {"type": self.return_type},
            },
            "comparison": self.comparison,
            "examples": [e.model_dump() for e in self.examples],
            "source": "synthetic",
        }


def parse_problem(text: str, category: str = "", difficulty: str = "Easy") -> SynthProblem:
    """Parses a model reply into a validated problem. Raises ValueError on any problem."""
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start, end = stripped.find("{"), stripped.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in the reply")
    data = json.loads(stripped[start : end + 1])
    data.setdefault("category", category)
    data["difficulty"] = difficulty
    problem = SynthProblem.model_validate(data)
    problem.check_examples()
    return problem


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def is_duplicate(vector: Sequence[float], accepted: Sequence[Sequence[float]]) -> float | None:
    """The highest similarity to an accepted statement if it reaches the threshold, else None."""
    best = max((cosine(vector, v) for v in accepted), default=0.0)
    return best if best >= SIMILARITY_THRESHOLD else None


def estimate_cost(count: int, usd_per_1m_input: float = 0.0, usd_per_1m_output: float = 0.0) -> str:
    attempts = count * 1.3  # some retries and duplicates
    tin, tout = attempts * EST_INPUT_TOKENS, attempts * EST_OUTPUT_TOKENS
    usd = tin / 1e6 * usd_per_1m_input + tout / 1e6 * usd_per_1m_output
    return (
        f"~{attempts:.0f} LLM calls, ~{tin / 1000:.0f}k input and ~{tout / 1000:.0f}k output tokens"
        f" (about ${usd:.2f} at the given prices; $0 on a local model)"
    )


async def generate_problems(
    count: int,
    llm: LLM,
    embed: Callable[[Sequence[str]], Awaitable[list[list[float]]]],
    out_dir: Path = PROBLEMS_DIR,
    *,
    seed: int = 1,
    log: Callable[[str], None] = print,
) -> list[SynthProblem]:
    """Generates up to `count` accepted problems, cycling through categories and difficulties."""
    system, template = load_ml_prompt("synth_problem_v1")
    out_dir.mkdir(parents=True, exist_ok=True)
    accepted: list[SynthProblem] = []
    vectors: list[list[float]] = []
    titles: set[str] = set()
    slugs = {p.stem for p in out_dir.glob("*.json")}
    for path in out_dir.glob("*.json"):  # resume: existing problems count towards dedupe
        old = json.loads(path.read_text())
        titles.add(old["title"].lower())
        vectors += await embed([old["content_text"]])
    rejected = {"invalid": 0, "duplicate": 0}
    i = 0
    while len(accepted) < count and i < count * 3:
        category = CATEGORIES[i % len(CATEGORIES)]
        difficulty = DIFFICULTIES[i % len(DIFFICULTIES)]
        i += 1
        feedback = ""
        for _ in range(MAX_ATTEMPTS_PER_PROBLEM):
            existing = "\n".join(f"- {t}" for t in sorted(titles)[-40:]) or "(none yet)"
            user = render(template, {
                "category": category, "difficulty": difficulty, "seed": seed * 1000 + i,
                "existing": existing, "feedback": feedback,
            })  # fmt: skip
            try:
                messages = [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ]
                problem = parse_problem(await llm(messages), category, difficulty)
            except (ValueError, TypeError) as exc:
                rejected["invalid"] += 1
                feedback = f"Your previous answer was invalid ({str(exc)[:200]}). Fix it."
                continue
            statement = problem.to_pipeline_problem()["content_text"]
            vector = (await embed([statement]))[0]
            if problem.slug in slugs or problem.title.lower() in titles:
                dup: float | None = 1.0
            else:
                dup = is_duplicate(vector, vectors)
            if dup is not None:
                rejected["duplicate"] += 1
                feedback = "That problem is too similar to an existing one. Invent a different one."
                continue
            accepted.append(problem)
            vectors.append(vector)
            titles.add(problem.title.lower())
            slugs.add(problem.slug)
            (out_dir / f"{problem.slug}.json").write_text(
                json.dumps(problem.to_pipeline_problem(), indent=2) + "\n"
            )
            log(f"[{len(accepted)}/{count}] {problem.slug} ({category})")
            break
    log(f"accepted {len(accepted)}; rejected {rejected}")
    return accepted


async def amain(args: argparse.Namespace) -> int:
    from app.config import get_settings
    from app.llm.gateway import complete
    from app.rag.embedder import get_embedder

    count = args.limit or args.count
    print("estimate:", estimate_cost(count, args.usd_in, args.usd_out))
    if not args.yes and count > 10:
        print("Full-size run: re-run with --yes to confirm (this makes real LLM calls).")
        return 0
    settings = get_settings()
    if settings.aporia_llm_mock:
        print("APORIA_LLM_MOCK is set: unset it to use a real model.", file=sys.stderr)
        return 2
    embedder = get_embedder()
    if embedder is None:
        print("Set APORIA_EMBEDDING_MODEL (used to deduplicate).", file=sys.stderr)
        return 2

    async def llm(messages: list[dict[str, str]]) -> str:
        return await complete(messages, "APORIA_MODEL_STRONG")

    await generate_problems(count, llm, embedder.embed, seed=args.seed)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--count", type=int, default=150)
    ap.add_argument("--limit", type=int, default=0, help="generate only this many (quick check)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--usd-in", type=float, default=0.0, help="USD per 1M input tokens")
    ap.add_argument("--usd-out", type=float, default=0.0, help="USD per 1M output tokens")
    ap.add_argument("--yes", action="store_true", help="confirm a full-size run")
    return asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
