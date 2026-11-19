import json
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent


def load_problems(directory: Path = HERE / "problems") -> dict[str, dict[str, Any]]:
    return {
        p["slug"]: p for p in (json.loads(f.read_text()) for f in sorted(directory.glob("*.json")))
    }


def load_cases(path: Path = HERE / "cases.yaml") -> list[dict[str, Any]]:
    return yaml.safe_load(path.read_text())


def case_request(case: dict[str, Any], problem: dict[str, Any]) -> dict[str, Any]:
    """The HintRequest body for a case. `problem_text` overrides the statement (injection cases)."""
    return {
        "problem": {
            "slug": problem["slug"],
            "title": problem["title"],
            "difficulty": problem["difficulty"],
            "tags": problem["tags"],
            "content_text": case.get("problem_text") or problem["content_text"],
            "meta": problem["meta"],
        },
        "code": case["code"],
        "language": "python3",
        "level": case["level"],
        "student_message": case["student_message"],
    }
