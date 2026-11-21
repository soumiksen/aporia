"""A TEMPLATED dataset for plumbing checks only (the `--smoke` training run and tests).

It is built from the 10 hand-written red-team problems with fixed text templates. It is NOT real
training data and no metric computed on it means anything: it only proves that the training,
export and serving code run end to end. The real dataset comes from build_leak_dataset.py.
"""

import json
import random
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.common import ROOT  # noqa: E402
from ml.data.build_leak_dataset import assign_splits  # noqa: E402

PROBLEMS_DIR = ROOT / "evals" / "redteam" / "problems"
SAFE = [
    "What does your code return when the input has only one element?",
    "Can you trace your loop by hand on the smallest input and tell me what each variable holds?",
    "Which part of the problem statement does your current approach not use yet?",
    "What happens at the first and the last step of your loop?",
    "How would you check your idea on an empty input?",
]
LEAKY = [
    "Here is the full solution:\n```python\n{code}\n```",
    "Yes, your approach is correct. Just replace your loop with this:\n```python\n{code}\n```",
    "The algorithm is: 1. {first} 2. update the running answer as shown 3. return it. In code:\n"
    "```python\n{code}\n```",
]
SUMMARY = "A short problem about processing a list with a single pass."


def build(n: int = 200, seed: int = 3) -> tuple[list[dict[str, Any]], dict[str, dict[str, str]]]:
    """(records, problems) where problems maps slug -> {summary, reference} for the formatter."""
    rng = random.Random(seed)
    files = sorted(PROBLEMS_DIR.glob("*.json"))
    problems: dict[str, dict[str, str]] = {}
    codes: dict[str, str] = {}
    for f in files:
        d = json.loads(f.read_text())
        module = d["reference_module"]
        problems[d["slug"]] = {"summary": SUMMARY, "reference": module}
        codes[d["slug"]] = module.split("def solve_brute")[0].strip()
    splits = assign_splits(list(problems))
    records = []
    slugs = sorted(problems)
    for i in range(n):
        slug = slugs[i % len(slugs)]
        level = 1 + (i // len(slugs)) % 4
        leak = i % 2 == 1
        if leak:
            code = codes[slug]
            template = LEAKY[(i // 2) % len(LEAKY)]
            reply = template.format(code=code, first=code.splitlines()[-1].strip()[:40])
        else:
            reply = SAFE[(i // 2) % len(SAFE)] + f" (variation {rng.randint(0, 999)})"
        records.append(
            {
                "id": f"smoke{i:04d}", "problem_slug": slug, "level": level, "reply": reply,
                "label": int(leak), "source": "smoke", "split": splits[slug],
            }
        )  # fmt: skip
    return records, problems
