"""Checks the real dataset file: splits grouped by problem, balance, per-level coverage, size.

    uv --directory apps/api run python ../../ml/data/validate_dataset.py [path] [--min-records 3000]
Exit code 1 on any hard problem.
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.data.build_leak_dataset import BALANCE_TOLERANCE, LEVELS, OUT  # noqa: E402

REQUIRED = {"id", "problem_slug", "level", "reply", "label", "source", "split"}


def check(records: list[dict[str, Any]], min_records: int = 0) -> list[str]:
    """Hard problems found in the records (empty list when the dataset is fine)."""
    problems: list[str] = []
    if not records:
        return ["the dataset is empty"]
    for r in records:
        if not REQUIRED <= r.keys():
            missing = sorted(REQUIRED - r.keys())
            return [f"record {r.get('id')} is missing fields {missing}"]
    ids = [r["id"] for r in records]
    if len(set(ids)) != len(ids):
        problems.append("duplicate ids")
    if any(r["label"] not in (0, 1) or r["level"] not in LEVELS for r in records):
        problems.append("labels must be 0/1 and levels 1-4")
    if any(not r["reply"].strip() for r in records):
        problems.append("empty replies")
    by_problem: dict[str, set[str]] = defaultdict(set)
    for r in records:
        by_problem[r["problem_slug"]].add(r["split"])
    leaked = sorted(p for p, s in by_problem.items() if len(s) > 1)
    if leaked:
        problems.append(f"problems appear in more than one split: {leaked[:5]}")
    positives = sum(r["label"] for r in records) / len(records)
    if abs(positives - 0.5) > BALANCE_TOLERANCE:
        problems.append(f"labels are not balanced: {positives:.1%} leak")
    for level in LEVELS:
        labels = {r["label"] for r in records if r["level"] == level}
        if labels != {0, 1}:
            problems.append(f"level {level} lacks one of the classes")
    for split in ("train", "val", "test"):
        if not any(r["split"] == split for r in records):
            problems.append(f"no records in split {split}")
    if len(records) < min_records:
        problems.append(f"only {len(records)} records (need at least {min_records})")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", nargs="?", default=str(OUT))
    ap.add_argument("--min-records", type=int, default=3000)
    args = ap.parse_args()
    path = Path(args.path)
    if not path.exists():
        print(f"{path} does not exist: build it first (build_leak_dataset.py)")
        return 1
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    problems = check(records, args.min_records)
    for p in problems:
        print("PROBLEM:", p)
    print(f"{len(records)} records checked, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
