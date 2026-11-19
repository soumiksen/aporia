import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redteam.loaders import load_cases, load_problems  # noqa: E402
from redteam.score import deterministic_score  # noqa: E402

CASES = {c["id"]: c for c in load_cases()}
PROBLEMS = load_problems()


def no_leak(output, context):
    case = CASES[context["vars"]["case_id"]]
    score = deterministic_score(
        output, case["level"], PROBLEMS[case["problem_slug"]]["reference_module"]
    )
    return {
        "pass": not score["leaked"],
        "score": 0 if score["leaked"] else 1,
        "reason": f"signals: {score['signals']}",
    }
