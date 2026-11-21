"""Loads the dataset and the per-problem texts the formatter needs, and tokenizes records."""

import hashlib
import json
from pathlib import Path
from typing import Any

from app.guard.classifier_format import MAX_TOKENS, format_input, reference_text

from ml.common import ROOT

REFERENCES_DIR = ROOT / "ml" / "data" / "references"
REDTEAM_PROBLEMS = ROOT / "evals" / "redteam" / "problems"


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def load_problem_texts(directories: list[Path] | None = None) -> dict[str, dict[str, str]]:
    """slug -> {summary, reference} from verified reference files (and the red-team problems)."""
    out: dict[str, dict[str, str]] = {}
    for directory in directories or [REFERENCES_DIR, REDTEAM_PROBLEMS]:
        for f in sorted(directory.glob("*.json")):
            d = json.loads(f.read_text())
            if "reference_module" not in d:
                continue
            out[d["slug"]] = {
                "summary": d.get("concept_summary") or d.get("title", ""),
                "reference": d["reference_module"],
            }
    return out


class HFTokenizerAdapter:
    """The slice of a Hugging Face tokenizer the formatter uses."""

    def __init__(self, tokenizer: Any) -> None:
        self.tokenizer = tokenizer

    def encode(self, text: str) -> list[int]:
        return self.tokenizer.encode(text, add_special_tokens=False)

    def decode(self, ids: list[int]) -> str:
        return self.tokenizer.decode(ids, skip_special_tokens=True)


def format_records(
    records: list[dict[str, Any]],
    problems: dict[str, dict[str, str]],
    tokenizer: Any,
    max_tokens: int = MAX_TOKENS,
) -> list[str]:
    """Classifier input text for every record (identical to what the API builds at inference)."""
    adapter = HFTokenizerAdapter(tokenizer)
    texts = []
    for r in records:
        p = problems[r["problem_slug"]]
        texts.append(
            format_input(
                r["level"], p["summary"], reference_text(p["reference"]), r["reply"], adapter
            )
        )
    return texts


__all__ = ["MAX_TOKENS", "read_jsonl", "file_hash", "load_problem_texts", "format_records"]
