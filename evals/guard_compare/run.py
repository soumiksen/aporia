"""Compares the three guard modes (prompted, classifier_only, cascade).

(a) the held-out test split of the leak dataset, (b) replies from the Stage 2 red-team runs (labeled
only where the deterministic check and the LLM judge agreed). Writes `docs/results/guard.md`.

Needs a trained, exported classifier and a real judge model (it makes real LLM calls):

    cd apps/api
    APORIA_CLASSIFIER_DIR=../../ml/artifacts/onnx \
      uv run python ../../evals/guard_compare/run.py [--limit N]

Cost: judge calls are priced by LiteLLM; a local model costs $0. The classifier runs on CPU, so its
cost is its latency (reported), not dollars.
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from guard_compare.metrics import aggregate, render_markdown  # noqa: E402

OUT = ROOT / "docs" / "results" / "guard.md"
MODES = ("prompted", "classifier_only", "cascade")
DATASET = ROOT / "ml" / "data" / "leak_dataset.jsonl"
REDTEAM_RESULTS = ROOT / "evals" / "redteam" / "results"


async def evaluate_mode(
    mode: str, items: list[dict[str, Any]], decide: Any
) -> list[dict[str, Any]]:
    """Runs `decide(item, mode)` -> (predicted_leak, path, cost_usd) for every item, timing each."""
    out = []
    for item in items:
        start = time.perf_counter()
        predicted, path, cost = await decide(item, mode)
        out.append(
            {
                "label": item["label"],
                "predicted": int(predicted),
                "latency_ms": (time.perf_counter() - start) * 1000,
                "cost_usd": cost,
                "path": path,
            }
        )
    return out


def interpret(sections: dict[str, dict[str, dict[str, Any]]]) -> str:
    """Plain sentences built only from the measured numbers (no claims beyond them)."""
    first = next(iter(sections.values()))
    p, c = first["prompted"], first["cascade"]
    co = first["classifier_only"]

    def pct(v: float | None) -> str:
        return "n/a" if v is None else f"{v:.1%}"

    return (
        f"On the first set the cascade caught {pct(c['recall'])} of leaks with a "
        f"{pct(c['false_positive_rate'])} false-positive rate, against {pct(p['recall'])} and "
        f"{pct(p['false_positive_rate'])} for the prompted guard and {pct(co['recall'])} and "
        f"{pct(co['false_positive_rate'])} for the classifier alone. The cascade sent "
        f"{pct(c['judge_share'])} of checks to the judge, with a p95 latency of "
        f"{c['p95_ms']:.0f} ms against {p['p95_ms']:.0f} ms for the prompted guard. "
        "These come from one run on one dataset and labels from our own pipeline; treat small "
        "differences as noise."
    )


async def amain(args: argparse.Namespace) -> int:
    from app.config import get_settings
    from app.guard.cascade import cascade_check
    from app.guard.classifier import get_classifier
    from app.guard.llm_judge import instructor_judge
    from app.llm import calls
    from app.schemas.hint import ProblemContext
    from ml.data.build_leak_dataset import redteam_records
    from ml.train.data import load_problem_texts, read_jsonl

    settings = get_settings()
    classifier = get_classifier()
    if classifier is None:
        print("No classifier: set APORIA_CLASSIFIER_DIR to an exported model (see ml/README.md).")
        print("Leaving docs/results/guard.md as the TODO placeholder.")
        return 2
    if settings.aporia_llm_mock:
        print("APORIA_LLM_MOCK is set: the judge needs a real model.", file=sys.stderr)
        return 2

    async def discard(rec: Any) -> None:
        return None

    calls.set_writer(discard)  # do not write comparison calls into llm_calls
    problems = load_problem_texts()
    statements = {}
    for d in (ROOT / "evals" / "redteam" / "problems").glob("*.json"):
        p = json.loads(d.read_text())
        statements[p["slug"]] = p
    for d in (ROOT / "ml" / "data" / "references").glob("*.json"):
        p = json.loads(d.read_text())
        statements[p["slug"]] = p

    async def decide(item: dict[str, Any], mode: str) -> tuple[bool, str, float]:
        slug = item["problem_slug"]
        meta = statements[slug]
        problem = ProblemContext(
            slug=slug, title=meta["title"], difficulty=meta.get("difficulty", "Easy"),
            tags=meta.get("tags", []), content_text=meta["content_text"],
        )  # fmt: skip
        bucket: list[Any] = []
        token = calls.accumulator.set(bucket)
        try:
            decision = await cascade_check(
                item["reply"], item["level"], problem, problems[slug]["reference"],
                instructor_judge, mode=mode, classifier=classifier,
                summary=problems[slug]["summary"],
            )  # fmt: skip
        finally:
            calls.accumulator.reset(token)
        return decision.leaks, decision.path, sum(r.cost_usd for r in bucket)

    sections: dict[str, dict[str, dict[str, Any]]] = {}
    test = (
        [r for r in read_jsonl(Path(args.data)) if r["split"] == "test"]
        if Path(args.data).exists()
        else []
    )
    if args.limit:
        test = test[: args.limit]
    red = redteam_records(REDTEAM_RESULTS, set(problems))
    if args.limit:
        red = red[: args.limit]
    for title, items in (("Held-out test split", test), ("Stage 2 red-team replies", red)):
        if not items:
            continue
        sections[title] = {}
        for mode in MODES:
            print(f"{title}: {mode} ({len(items)} items)")
            sections[title][mode] = aggregate(await evaluate_mode(mode, items, decide))
    if not sections:
        print("no evaluation data found (build the dataset / run the red-team suite first)")
        return 2
    card = classifier.card
    meta = {
        "Classifier": f"`{card.get('base_model', '?')}` "
        f"(dataset hash `{card.get('dataset_hash', '?')}`)",
        "Thresholds": f"t_low = {classifier.t_low:.3f}, t_high = {classifier.t_high:.3f}",
        "Judge model": f"`{settings.aporia_model_judge}`",
        "Date": date.today().isoformat(),
    }
    text = render_markdown(
        sections, meta=meta, interpretation=interpret(sections), today=date.today().isoformat()
    )
    Path(args.out).write_text(text)
    print(text)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", default=str(DATASET))
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--out", default=str(OUT))
    return asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
