"""Measures execution grounding on the synthetic problem set (no network, no LLM).

Each synthetic problem is paired with a plausible wrong student solution (taken from the red-team
cases). Everything runs through the real finder, shrinker and harness, using a local subprocess
runner that is only suitable for these trusted synthetic programs.

usage (from the repo root):  uv --directory apps/api run python ../../evals/grounding/measure.py
"""

import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "api"))

from app.grounding.finder import ReferenceData, input_size  # noqa: E402
from app.grounding.service import ground  # noqa: E402
from tests.support.subprocess_runner import SubprocessRunner  # noqa: E402

from redteam.loaders import load_cases, load_problems  # noqa: E402


def wrong_solutions() -> dict[str, str]:
    """One plausible wrong attempt per problem: a case's code that is not a stub or a solution."""
    out: dict[str, str] = {}
    for case in load_cases():
        code = case["code"]
        if case["category"] in ("confirmation", "injection"):
            continue
        if "pass\n" in code or "..." in code or "TODO" in code:
            continue  # an empty stub is trivially wrong; we want a real attempt
        out.setdefault(case["problem_slug"], code)
    return out


async def measure() -> dict:
    problems = load_problems()
    solutions = wrong_solutions()
    runner = SubprocessRunner()
    rows = []
    for slug, problem in sorted(problems.items()):
        code = solutions.get(slug)
        if code is None:
            rows.append({"slug": slug, "status": "no_solution"})
            continue
        cases = [(list(e["args"]), e["expected"]) for e in problem["examples"]]
        reference = ReferenceData(problem["reference_module"], problem["comparison"], cases)
        started = time.monotonic()
        result = await ground(problem, code, "python3", reference, runner)
        elapsed = time.monotonic() - started
        failure = result.failure
        rows.append(
            {
                "slug": slug,
                "status": "grounded" if result.grounded else (result.error or "no_failure_found"),
                "kind": failure.kind if failure else None,
                "input_size": input_size(failure.input) if failure else None,
                "seconds": round(elapsed, 2),
            }
        )
    grounded = [r for r in rows if r["status"] == "grounded"]
    times = [r["seconds"] for r in rows if "seconds" in r]
    return {
        "problems": len(rows),
        "grounded": len(grounded),
        "success_rate": round(len(grounded) / len(rows), 3) if rows else None,
        "median_seconds": round(statistics.median(times), 2) if times else None,
        "max_seconds": max(times) if times else None,
        "rows": rows,
    }


def main() -> int:
    report = asyncio.run(measure())
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
