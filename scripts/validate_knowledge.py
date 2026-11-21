"""Validates knowledge/notes/*.md against knowledge/concepts.yaml.

Checks: frontmatter, section presence and order, 250-400 words, 4-6 Socratic questions, and that
every concept has a note (and every note a concept). Exit code 1 on any problem.

Run from the repo root: `cd apps/api && uv run python ../../scripts/validate_knowledge.py`.
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.rag.taxonomy import load_taxonomy  # noqa: E402

SECTIONS = [
    "Idea",
    "When it applies",
    "Common mistakes",
    "Socratic questions",
    "Tiny illustration",
    "Related concepts",
]
MIN_WORDS, MAX_WORDS = 250, 400
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.DOTALL)


def split_note(text: str) -> tuple[dict, str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError("missing frontmatter")
    meta = yaml.safe_load(m.group(1)) or {}
    return meta, m.group(2)


def sections_of(body: str) -> dict[str, str]:
    parts = re.split(r"^## (.+)$", body, flags=re.MULTILINE)
    return {parts[i].strip(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}


def validate_note(slug_from_file: str, text: str, known: set[str]) -> list[str]:
    problems: list[str] = []
    try:
        meta, body = split_note(text)
    except ValueError as exc:
        return [str(exc)]
    for key in ("slug", "concept", "reviewed"):
        if key not in meta:
            problems.append(f"frontmatter missing `{key}`")
    if meta.get("slug") != slug_from_file or meta.get("concept") != slug_from_file:
        problems.append("slug and concept must equal the file name")
    if slug_from_file not in known:
        problems.append("no such concept in concepts.yaml")
    if not isinstance(meta.get("reviewed"), bool):
        problems.append("`reviewed` must be true or false")
    secs = sections_of(body)
    if list(secs) != SECTIONS:
        problems.append(f"sections must be exactly {SECTIONS}, got {list(secs)}")
    words = len(re.findall(r"\b[\w'-]+\b", body))
    if not MIN_WORDS <= words <= MAX_WORDS:
        problems.append(f"{words} words (need {MIN_WORDS}-{MAX_WORDS})")
    questions = [ln for ln in secs.get("Socratic questions", "").splitlines() if ln.strip()]
    if not 4 <= len(questions) <= 6:
        problems.append(f"{len(questions)} Socratic questions (need 4-6)")
    for ln in questions:
        if not ln.strip().endswith("?"):
            problems.append(f"Socratic line is not a question: {ln.strip()[:50]}")
    for rel in re.findall(r"[a-z0-9-]+", secs.get("Related concepts", "")):
        if "-" in rel and rel not in known:
            problems.append(f"related concept `{rel}` is not in concepts.yaml")
    return problems


def main() -> int:
    known = set(load_taxonomy().slugs)
    notes_dir = ROOT / "knowledge" / "notes"
    files = {p.stem: p for p in sorted(notes_dir.glob("*.md"))}
    bad = 0
    for slug in sorted(known - files.keys()):
        print(f"MISSING note for concept {slug}")
        bad += 1
    for slug, path in files.items():
        problems = validate_note(slug, path.read_text(encoding="utf-8"), known)
        for p in problems:
            print(f"{path.name}: {p}")
        bad += bool(problems)
    print(f"{len(files)} notes, {len(known)} concepts, {bad} with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
