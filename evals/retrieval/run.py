"""Retrieval evaluation: precision@3/5, recall@5, MRR and latency for each retrieval mode.

Reads `pairs.csv` (query, relevant concept slugs), retrieves study notes in each mode, ranks
*concepts* (several chunks of one note count once) and writes `docs/results/retrieval.md`.

Needs the migrated database and the notes ingested (this script ingests them first; unchanged
chunks are not re-embedded). Uses the configured embedder (APORIA_EMBEDDING_MODEL); with
APORIA_LLM_MOCK=1 it uses the fake lexical embedder, which is only good for checking the plumbing.

usage (from the repo root):
    uv --directory apps/api run python ../../evals/retrieval/run.py [--limit N] [--modes vector fts]
"""

import argparse
import asyncio
import csv
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(ROOT / "apps" / "api"))

from retrieval.metrics import dedupe, summarize  # noqa: E402

PAIRS = HERE / "pairs.csv"
RESULTS = ROOT / "docs" / "results" / "retrieval.md"
MODES = ["vector", "fts", "hybrid", "hybrid_rerank"]
LABELED = "labeled"

Search = Callable[[str, str], Awaitable[list[str]]]  # (query, mode) -> ranked concept slugs


@dataclass(frozen=True)
class Pair:
    query_id: str
    query: str
    relevant: frozenset[str]
    status: str


def load_pairs(path: Path = PAIRS) -> list[Pair]:
    with path.open(newline="") as f:
        return [
            Pair(
                r["query_id"],
                r["query"],
                frozenset(s for s in r["relevant_slugs"].split("|") if s),
                r.get("status", "needs_human_label"),
            )
            for r in csv.DictReader(f)
        ]


async def evaluate(
    pairs: list[Pair], search: Search, modes: list[str]
) -> dict[str, dict[str, float]]:
    """Runs every query in every mode, timing each search."""
    out: dict[str, dict[str, float]] = {}
    for mode in modes:
        rankings: list[list[str]] = []
        latencies: list[float] = []
        for pair in pairs:
            start = time.perf_counter()
            ranking = await search(pair.query, mode)
            latencies.append((time.perf_counter() - start) * 1000)
            rankings.append(dedupe(ranking))
        out[mode] = summarize(rankings, [set(p.relevant) for p in pairs], latencies)
    return out


def render_markdown(
    results: dict[str, dict[str, float]],
    pairs: list[Pair],
    *,
    embedder: str,
    skipped: dict[str, str],
    today: str | None = None,
) -> str:
    labeled = sum(1 for p in pairs if p.status == LABELED)
    provisional = labeled < len(pairs)
    lines = [
        "# Retrieval evaluation",
        "",
        f"Generated {today or date.today().isoformat()} by `evals/retrieval/run.py`.",
        "",
        f"- Queries: {len(pairs)} ({labeled} human-labeled)",
        f"- Embedder: `{embedder}`",
        "- Corpus: concept study notes (chunked by section); concepts are ranked, a concept counts "
        "once however many of its chunks are retrieved",
    ]
    if provisional:
        lines += [
            "",
            "> **Provisional.** The relevance labels in `evals/retrieval/pairs.csv` are drafts "
            f"(only {labeled} of {len(pairs)} rows are `labeled`). Do not treat these numbers as "
            "final until the labels have been reviewed and corrected by a human.",
        ]
    lines += [
        "",
        "| mode | P@3 | P@5 | R@5 | MRR | p50 ms | p95 ms |",
        "|---|---|---|---|---|---|---|",
    ]
    for mode in MODES:
        if mode in results:
            r = results[mode]
            lines.append(
                f"| {mode} | {r['p@3']:.3f} | {r['p@5']:.3f} | {r['r@5']:.3f} | {r['mrr']:.3f} "
                f"| {r['p50_ms']:.0f} | {r['p95_ms']:.0f} |"
            )
        elif mode in skipped:
            lines.append(f"| {mode} | - | - | - | - | - | - |")
    for mode, why in skipped.items():
        lines.append(f"\n`{mode}` skipped: {why}.")
    lines += [
        "",
        "P@k is the share of the top k concepts that are relevant; R@5 is the share of the "
        "relevant concepts found in the top 5; MRR is the mean reciprocal rank of the first "
        "relevant concept. Latency includes embedding the query (cached embeddings make repeat "
        "runs faster).",
        "",
    ]
    return "\n".join(lines)


async def amain(args: argparse.Namespace) -> int:
    import redis.asyncio
    from app.config import get_settings
    from app.db import SessionLocal
    from app.rag.embedder import get_embedder
    from app.rag.ingest import ingest_notes
    from app.rag.rerank import BgeReranker
    from app.rag.retrieve import retrieve

    settings = get_settings()
    client = redis.asyncio.Redis.from_url(settings.redis_url)
    try:
        embedder = get_embedder(client)
        if embedder is None:
            print("Set APORIA_EMBEDDING_MODEL (or APORIA_LLM_MOCK=1 for the fake embedder).")
            return 2
        stats = await ingest_notes(SessionLocal, embedder)
        print(f"notes: {stats}")

        pairs = load_pairs()[: args.limit] if args.limit else load_pairs()
        skipped: dict[str, str] = {}
        modes = [m for m in args.modes if m in MODES]
        reranker: Any = None
        if "hybrid_rerank" in modes:
            if settings.aporia_rerank:
                reranker = BgeReranker()
            else:
                modes.remove("hybrid_rerank")
                skipped["hybrid_rerank"] = "APORIA_RERANK is not 1 (reranker disabled)"

        async def search(query: str, mode: str) -> list[str]:
            async with SessionLocal() as session:
                hits = await retrieve(
                    session, embedder, query, "notes", 10, mode,  # type: ignore[arg-type]
                    reranker=reranker,
                )  # fmt: skip
            return [h.slug for h in hits]

        results = await evaluate(pairs, search, modes)
        text = render_markdown(results, pairs, embedder=embedder.model, skipped=skipped)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text)
        print(text)
        print(f"wrote {out}")
        return 0
    finally:
        await client.aclose()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--limit", type=int, default=0, help="only the first N queries")
    ap.add_argument("--modes", nargs="+", default=MODES, choices=MODES)
    ap.add_argument("--out", default=str(RESULTS))
    return asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
