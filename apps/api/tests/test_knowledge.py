import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "validate_knowledge", ROOT / "scripts/validate_knowledge.py"
)
assert spec and spec.loader
vk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vk)

KNOWN = {"stack", "sliding-window"}


def note(
    questions: str = "- a?\n- b?\n- c?\n- d?", reviewed: str = "false", slug: str = "stack"
) -> str:
    parts = []
    for h in vk.SECTIONS:
        body = questions if h == "Socratic questions" else "word " * 60
        parts.append(f"## {h}\n{body}")
    return (
        f"---\nslug: {slug}\nconcept: {slug}\nreviewed: {reviewed}\n---\n"
        + "\n\n".join(parts)
        + "\n"
    )


def test_valid_note_passes() -> None:
    assert vk.validate_note("stack", note(), KNOWN) == []


def test_problems_are_reported() -> None:
    assert any(
        "sections" in p
        for p in vk.validate_note("stack", note().replace("## Idea", "## Intro"), KNOWN)
    )
    assert any(
        "words" in p for p in vk.validate_note("stack", note().replace("word " * 60, "word"), KNOWN)
    )
    assert any(
        "Socratic questions" in p for p in vk.validate_note("stack", note("- a?\n- b?"), KNOWN)
    )
    assert any(
        "not a question" in p
        for p in vk.validate_note("stack", note("- a?\n- b\n- c?\n- d?"), KNOWN)
    )
    assert any("reviewed" in p for p in vk.validate_note("stack", note(reviewed="maybe"), KNOWN))
    assert any("file name" in p for p in vk.validate_note("other", note(), KNOWN | {"other"}))
    assert any("no such concept" in p for p in vk.validate_note("zzz", note(slug="zzz"), KNOWN))
    assert vk.validate_note("stack", "no frontmatter", KNOWN) == ["missing frontmatter"]


def test_real_notes_all_validate_and_start_unreviewed() -> None:
    assert vk.main() == 0
    unreviewed = [
        p for p in (ROOT / "knowledge/notes").glob("*.md") if "reviewed: false" in p.read_text()
    ]
    assert len(unreviewed) >= 1 or pytest.skip("all notes have been reviewed")
