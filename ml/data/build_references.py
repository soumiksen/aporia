"""Verifies a reference solution for every synthetic problem (Stage 2 pipeline), keeps verified.

Untrusted model-written code runs only through the Judge0 sandbox, so this needs a working Judge0
(a Linux host; see docs/DECISIONS.md). Costs LLM calls (strong model). Run it yourself:
    uv --directory apps/api run python ../../ml/data/build_references.py --limit 3
    uv --directory apps/api run python ../../ml/data/build_references.py
Output: `ml/data/references/<slug>.json` (verified only) and a verification-rate summary.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.common import API_DIR  # noqa: E402,F401

HERE = Path(__file__).resolve().parent
PROBLEMS_DIR = HERE / "problems"
REFERENCES_DIR = HERE / "references"

LLM = Callable[[list[dict[str, str]]], Awaitable[str]]


async def build_all(
    problem_files: list[Path],
    llm: LLM,
    runner: Any,
    out_dir: Path = REFERENCES_DIR,
    *,
    concurrency: int = 2,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    """Runs `build_reference` per problem. Infrastructure errors are not counted as failures."""
    from app.reference.pipeline import build_reference

    out_dir.mkdir(parents=True, exist_ok=True)
    sem = asyncio.Semaphore(concurrency)
    stats: dict[str, Any] = {
        "total": 0,
        "verified": 0,
        "failed": 0,
        "infra_errors": 0,
        "reasons": {},
    }

    async def one(path: Path) -> None:
        problem = json.loads(path.read_text())
        async with sem:
            result = await build_reference(problem, llm=llm, runner=runner)
        stats["total"] += 1
        if result.infrastructure_error:
            stats["infra_errors"] += 1
            log(f"{problem['slug']}: infrastructure error ({result.reason}); not counted")
            return
        if result.status != "verified":
            stats["failed"] += 1
            reason = str(result.reason)
            stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
            log(f"{problem['slug']}: failed ({reason})")
            return
        stats["verified"] += 1
        record = {
            **problem,
            "reference_module": result.module_source,
            "comparison": result.comparison,
            "examples": result.examples,
            "verified_cases": result.verified_cases,
        }
        (out_dir / f"{problem['slug']}.json").write_text(json.dumps(record, indent=2) + "\n")
        log(f"{problem['slug']}: verified ({result.verified_cases} cases)")

    await asyncio.gather(*(one(p) for p in problem_files))
    judged = stats["verified"] + stats["failed"]
    stats["verification_rate"] = stats["verified"] / judged if judged else None
    return stats


async def amain(args: argparse.Namespace) -> int:
    from app.config import get_settings
    from app.llm.gateway import complete
    from app.sandbox.judge0 import Judge0Runner

    settings = get_settings()
    if settings.aporia_llm_mock:
        print("APORIA_LLM_MOCK is set: unset it to use a real model.", file=sys.stderr)
        return 2
    files = sorted(PROBLEMS_DIR.glob("*.json"))
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("no problems found: run ml/data/synth_problems.py first", file=sys.stderr)
        return 2
    print(
        f"{len(files)} problems; about {len(files) * 6} strong-model calls (analyze, write, repair)"
    )

    async def llm(messages: list[dict[str, str]]) -> str:
        return await complete(messages, "APORIA_MODEL_STRONG")

    stats = await build_all(files, llm, Judge0Runner(settings.judge0_url))
    rate = stats["verification_rate"]
    print(json.dumps(stats, indent=2))
    print(f"verification rate: {rate:.0%}" if rate is not None else "verification rate: n/a")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--limit", type=int, default=0)
    return asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
