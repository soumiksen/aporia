"""Builds the leak-classifier dataset (`ml/data/leak_dataset.jsonl`).

One record per {id, problem_slug, level, reply, label, source, split}. Sources:
  safe       Socratic replies at each level (strong model).
  leaky      replies the model is told to make leaky in six different ways.
  redteam    guard-off replies from the Stage 2 red-team runs, kept only where the deterministic
             similarity check and the LLM judge agree.
  hardneg    safe replies that mention data structures, complexity or short non-solution snippets.

Costs LLM calls (about 48 per problem at the defaults). A cost estimate is printed first.
    uv --directory apps/api run python ../../ml/data/build_leak_dataset.py --limit-problems 3
    uv --directory apps/api run python ../../ml/data/build_leak_dataset.py --yes
Needs verified problems in ml/data/references/ (see build_references.py).
"""

import argparse
import asyncio
import hashlib
import json
import random
import sys
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.common import ROOT, load_ml_prompt, render  # noqa: E402

HERE = Path(__file__).resolve().parent
REFERENCES_DIR = HERE / "references"
OUT = HERE / "leak_dataset.jsonl"
REDTEAM_RESULTS = ROOT / "evals" / "redteam" / "results"
REDTEAM_PROBLEMS = ROOT / "evals" / "redteam" / "problems"
LEVELS = (1, 2, 3, 4)
SPLIT_FRACTIONS = (0.70, 0.15, 0.15)
BALANCE_TOLERANCE = 0.05
MIN_REPLY_CHARS = 25
LLM = Callable[[list[dict[str, str]]], Awaitable[str]]

LEVEL_RULES = {
    1: "Level 1 (nudge): exactly one guiding question, at most two sentences. No code.",
    2: "Level 2 (hint): point at a kind of input or a broad concept. No approach, no steps, "
    "no code.",
    3: "Level 3 (explanation): describe the general idea in words. No code, no line-by-line "
    "algorithm, no exact fix.",
    4: "Level 4 (worked example): invent a DIFFERENT small problem on the same concepts and solve "
    "it step by step. Never solve the student's own problem.",
}
SAFE_STYLES = [
    "Ask a question about a tiny input the student can trace by hand.",
    "Ask what the code does on an edge case such as an empty or one-item input.",
    "Ask the student to explain, in words, what one variable holds after each step.",
    "Ask what property of the problem the current approach does not yet use.",
]
HARD_NEGATIVE_STYLES = [
    "Mention a data structure by name (for example a stack, a queue or a hash map) as something "
    "the student has met, without saying it is the answer, and ask a question.",
    "Talk about time and space complexity in general terms, and ask the student to estimate the "
    "cost of their own loop.",
    "Include a short generic snippet of at most 2 lines that shows a language feature (for example "
    "how to iterate with an index) and is NOT part of any solution, then ask a question.",
]
LEAK_KINDS = {
    "full_code": "Give a complete, working solution in Python, in a fenced code block.",
    "partial_code": "Give the key lines of the solution (the crucial loop body or update rule) "
    "in a fenced code block, and say where they go.",
    "pseudocode": "Give step-by-step pseudocode of the exact algorithm that solves the problem.",
    "confirmation": "Confirm that the student's code is correct (or point at the exact line to "
    "change) and say it will pass the tests.",
    "other_language": "Give a complete working solution in a language other than Python (for "
    "example Java or C++), in a fenced code block.",
    "prose_steps": "Describe the exact algorithm in prose as numbered steps, naming the data "
    "structure and every update, so it can be coded directly.",
}


@dataclass(frozen=True)
class Problem:
    slug: str
    title: str
    statement: str
    reference: str  # the reference module source
    summary: str  # concept summary (as the API would see it)
    student_code: str = "class Solution:\n    pass\n"


# ---- pure helpers (unit-tested) ----


def record_id(slug: str, level: int, source: str, kind: str, index: int) -> str:
    return hashlib.sha1(f"{slug}|{level}|{source}|{kind}|{index}".encode()).hexdigest()[:16]


def assign_splits(slugs: list[str], seed: int = 7) -> dict[str, str]:
    """Problem slug -> train/val/test, 70/15/15, deterministic. Every split gets at least one
    problem when there are three or more."""
    ordered = sorted(set(slugs))
    random.Random(seed).shuffle(ordered)
    n = len(ordered)
    n_val = max(1, round(n * SPLIT_FRACTIONS[1])) if n >= 3 else 0
    n_test = max(1, round(n * SPLIT_FRACTIONS[2])) if n >= 3 else 0
    n_train = n - n_val - n_test
    out = {}
    for i, slug in enumerate(ordered):
        out[slug] = "train" if i < n_train else "val" if i < n_train + n_val else "test"
    return out


def refused(reply: str) -> bool:
    low = reply.lower()
    return len(reply.strip()) < MIN_REPLY_CHARS or any(
        m in low for m in ("i can't help", "i cannot help", "i can’t help", "as an ai")
    )


def plausible_leak(kind: str, reply: str) -> bool:
    """A cheap check that a 'leaky' reply really contains what it was asked to contain."""
    from app.guard.heuristics import asserts_correctness, fenced_blocks

    if refused(reply):
        return False
    blocks = fenced_blocks(reply)
    if kind in ("full_code", "partial_code", "other_language"):
        return any(len([ln for ln in body.splitlines() if ln.strip()]) >= 2 for _, body in blocks)
    if kind == "confirmation":
        return asserts_correctness(reply) or "pass" in reply.lower() or "correct" in reply.lower()
    return len(reply.split()) >= 25  # pseudocode / prose steps


def plausible_safe(level: int, reply: str, reference: str) -> bool:
    """A 'safe' reply must pass the deterministic guard (no solution code, no confirmation)."""
    from app.guard.heuristics import check_heuristics

    return not refused(reply) and not check_heuristics(reply, level, reference).blocked


def balance(records: list[dict[str, Any]], seed: int = 11) -> list[dict[str, Any]]:
    """Downsamples the majority class inside every (split, level) cell to a 50/50 mix, so each
    level and split keeps both classes."""
    rng = random.Random(seed)
    cells: dict[tuple[str, int], dict[int, list[dict[str, Any]]]] = {}
    for r in records:
        cells.setdefault((r["split"], r["level"]), {0: [], 1: []})[r["label"]].append(r)
    out: list[dict[str, Any]] = []
    for cell in cells.values():
        n = min(len(cell[0]), len(cell[1]))
        for label in (0, 1):
            group = sorted(cell[label], key=lambda r: r["id"])
            rng.shuffle(group)
            out += group[:n]
    return sorted(out, key=lambda r: r["id"])


def distribution(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total": len(records),
        "label": dict(Counter(r["label"] for r in records)),
        "level": dict(sorted(Counter(r["level"] for r in records).items())),
        "source": dict(Counter(r["source"] for r in records)),
        "split": dict(Counter(r["split"] for r in records)),
        "problems": len({r["problem_slug"] for r in records}),
    }


# ---- red-team source ----


def redteam_records(results_dir: Path, slugs: set[str] | None = None) -> list[dict[str, Any]]:
    """Guard-off replies labeled only where the deterministic check and the judge agree."""
    out: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        for rec in json.loads(path.read_text()).get("records", []):
            if rec.get("mode") != "guard_off" or rec.get("error") or not rec.get("reply"):
                continue
            det = (rec.get("deterministic") or {}).get("leaked")
            judge = (rec.get("judge") or {}).get("leaks")
            if det is None or judge is None or bool(det) != bool(judge):
                continue  # keep agreement cases only
            if slugs is not None and rec["problem_slug"] not in slugs:
                continue
            out.append(
                {
                    "problem_slug": rec["problem_slug"],
                    "level": int(rec.get("level_served") or rec["level"]),
                    "reply": rec["reply"],
                    "label": int(bool(det)),
                    "source": "redteam",
                    "kind": rec.get("case_id", ""),
                }
            )
    return out


# ---- generation ----


async def generate_records(
    problems: list[Problem],
    llm: LLM,
    *,
    safe_per_cell: int = 4,
    leaky_per_kind: int = 1,
    hardneg_per_level: int = 2,
    concurrency: int = 4,
    log: Callable[[str], None] = print,
) -> list[dict[str, Any]]:
    safe_sys, safe_tpl = load_ml_prompt("leak_safe_v1")
    leak_sys, leak_tpl = load_ml_prompt("leak_leaky_v1")
    sem = asyncio.Semaphore(concurrency)
    jobs: list[tuple[Problem, int, str, str, int]] = []  # problem, level, source, kind, index
    for p in problems:
        for level in LEVELS:
            for i in range(safe_per_cell):
                jobs.append((p, level, "safe", f"style{i % len(SAFE_STYLES)}", i))
            for i in range(hardneg_per_level):
                jobs.append((p, level, "hardneg", f"hn{i % len(HARD_NEGATIVE_STYLES)}", i))
            for kind in LEAK_KINDS:
                for i in range(leaky_per_kind):
                    jobs.append((p, level, "leaky", kind, i))
    rejected = Counter()

    async def one(job: tuple[Problem, int, str, str, int]) -> dict[str, Any] | None:
        p, level, source, kind, index = job
        seed = int(record_id(p.slug, level, source, kind, index)[:6], 16)
        if source == "leaky":
            system = leak_sys.replace("{kind_instruction}", LEAK_KINDS[kind])
            user = render(leak_tpl, {
                "title": p.title, "statement": p.statement, "reference": p.reference,
                "code": p.student_code, "level": level, "seed": seed,
            })  # fmt: skip
            system = render(system, {"kind_instruction": LEAK_KINDS[kind]})
        else:
            style = (
                SAFE_STYLES[int(kind[5:])]
                if source == "safe"
                else HARD_NEGATIVE_STYLES[int(kind[2:])]
            )
            system = render(safe_sys, {"level_rules": LEVEL_RULES[level], "style": style})
            user = render(safe_tpl, {
                "title": p.title, "statement": p.statement, "code": p.student_code, "seed": seed,
            })  # fmt: skip
        async with sem:
            try:
                reply = (
                    await llm(
                        [{"role": "system", "content": system}, {"role": "user", "content": user}]
                    )
                ).strip()
            except Exception:  # noqa: BLE001 - one failed call must not abort a long run
                rejected["llm_error"] += 1
                return None
        ok = (
            plausible_leak(kind, reply)
            if source == "leaky"
            else plausible_safe(level, reply, p.reference)
        )
        if not ok:
            rejected[f"{source}_filtered"] += 1
            return None
        return {
            "id": record_id(p.slug, level, source, kind, index),
            "problem_slug": p.slug, "level": level, "reply": reply,
            "label": 1 if source == "leaky" else 0,
            "source": "safe" if source == "safe" else source, "kind": kind,
        }  # fmt: skip

    done = [r for r in await asyncio.gather(*(one(j) for j in jobs)) if r]
    log(f"generated {len(done)} of {len(jobs)} requested; filtered/failed: {dict(rejected)}")
    return done


def finalize(
    generated: list[dict[str, Any]], extra: list[dict[str, Any]], seed: int = 7
) -> list[dict[str, Any]]:
    """Dedupes replies, assigns problem-grouped splits, balances classes, sorts by id."""
    seen: set[tuple[str, str]] = set()
    records: list[dict[str, Any]] = []
    for i, r in enumerate([*generated, *extra]):
        key = (r["problem_slug"], " ".join(r["reply"].split()))
        if key in seen:
            continue
        seen.add(key)
        r = dict(r)
        r.setdefault(
            "id", record_id(r["problem_slug"], r["level"], r["source"], r.get("kind", ""), i)
        )
        records.append(r)
    splits = assign_splits([r["problem_slug"] for r in records], seed)
    for r in records:
        r["split"] = splits[r["problem_slug"]]
    return [
        {k: r[k] for k in ("id", "problem_slug", "level", "reply", "label", "source", "split")}
        for r in balance(records)
    ]


def dataset_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def write_jsonl(records: list[dict[str, Any]], path: Path) -> None:
    path.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in records))


def estimate(n_problems: int, args: argparse.Namespace) -> tuple[int, str]:
    per = len(LEVELS) * (
        args.safe_per_cell + args.hardneg_per_level + len(LEAK_KINDS) * args.leaky_per_kind
    )
    calls = per * n_problems
    return (
        calls,
        f"~{calls} strong-model calls (~{calls * 0.9:.0f}k input, "
        f"~{calls * 0.35:.0f}k output tokens)",
    )


async def load_problems(limit: int) -> list[Problem]:
    """Verified synthetic problems (references dir), plus the 10 hand-written red-team problems."""
    from app.config import get_settings  # noqa: F401
    from app.llm.gateway import complete
    from app.rag.summarize import generate_summary, instructor_summary
    from app.rag.taxonomy import load_taxonomy

    taxonomy = load_taxonomy()
    files = sorted(REFERENCES_DIR.glob("*.json")) + sorted(REDTEAM_PROBLEMS.glob("*.json"))
    if limit:
        files = files[:limit]
    problems = []
    for f in files:
        d = json.loads(f.read_text())
        summary = d.get("concept_summary")
        if not summary:
            res = await generate_summary(
                d | {"content_text": d["content_text"]}, taxonomy, instructor_summary
            )
            summary = res.summary or d["title"]
            d["concept_summary"] = summary
            if f.parent == REFERENCES_DIR:
                f.write_text(json.dumps(d, indent=2) + "\n")
        problems.append(
            Problem(d["slug"], d["title"], d["content_text"], d["reference_module"], summary)
        )
    _ = complete
    return problems


async def amain(args: argparse.Namespace) -> int:
    from app.config import get_settings
    from app.llm.gateway import complete

    problems_preview = len(list(REFERENCES_DIR.glob("*.json"))) + len(
        list(REDTEAM_PROBLEMS.glob("*.json"))
    )
    n = min(args.limit_problems or problems_preview, problems_preview)
    calls, text = estimate(n, args)
    print(f"{n} problems: {text}")
    if not args.yes and calls > 300:
        print("Full-size run: re-run with --yes to confirm (this makes real LLM calls).")
        return 0
    if get_settings().aporia_llm_mock:
        print("APORIA_LLM_MOCK is set: unset it to use a real model.", file=sys.stderr)
        return 2
    problems = await load_problems(args.limit_problems)
    if not problems:
        print("no verified problems: run build_references.py first", file=sys.stderr)
        return 2

    async def llm(messages: list[dict[str, str]]) -> str:
        return await complete(messages, "APORIA_MODEL_STRONG")

    generated = await generate_records(
        problems, llm, safe_per_cell=args.safe_per_cell, leaky_per_kind=args.leaky_per_kind,
        hardneg_per_level=args.hardneg_per_level, concurrency=args.concurrency,
    )  # fmt: skip
    extra = (
        redteam_records(REDTEAM_RESULTS, {p.slug for p in problems}) if not args.no_redteam else []
    )
    print(f"red-team records kept (judge and similarity agree): {len(extra)}")
    records = finalize(generated, extra)
    write_jsonl(records, Path(args.out))
    print(json.dumps(distribution(records), indent=2))
    print(f"wrote {args.out} ({len(records)} records, hash {dataset_hash(Path(args.out))})")
    if len(records) < 3000:
        print("note: fewer than 3,000 records; increase the number of problems before training.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--limit-problems", type=int, default=0)
    ap.add_argument("--safe-per-cell", type=int, default=4)
    ap.add_argument("--leaky-per-kind", type=int, default=1)
    ap.add_argument("--hardneg-per-level", type=int, default=2)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--no-redteam", action="store_true")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--yes", action="store_true", help="confirm a full-size run")
    return asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
