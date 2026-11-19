import re

import pytest

from app.guard.safe_hints import SAFE_HINTS, safe_hint


def test_each_level_has_three_to_five_templates() -> None:
    assert set(SAFE_HINTS) == {1, 2, 3, 4}
    for level, templates in SAFE_HINTS.items():
        assert 3 <= len(templates) <= 5, level
        assert len(set(templates)) == len(templates)


def test_selection_is_deterministic_and_clamped() -> None:
    assert safe_hint("two-sum", 2) == safe_hint("two-sum", 2)
    assert safe_hint("x", 0) == safe_hint("x", 1)
    assert safe_hint("x", 9) == safe_hint("x", 4)
    assert safe_hint("x", 3) in SAFE_HINTS[3]


def test_selection_spreads_across_templates() -> None:
    picked = {safe_hint(f"problem-{i}", 1) for i in range(200)}
    assert len(picked) == len(SAFE_HINTS[1])


@pytest.mark.parametrize(
    ("level", "template"), [(lv, t) for lv, ts in SAFE_HINTS.items() for t in ts]
)
def test_templates_contain_no_code_or_verdicts(level: int, template: str) -> None:
    assert "```" not in template and "`" not in template
    assert not re.search(r"\b(def|return|for\s+\w+\s+in|while|class)\b\s*[\w(:]", template)
    assert not re.search(r"(that'?s|your (solution|code)) (is )?(correct|right)", template.lower())
    assert len(template.split()) <= 60
    assert template.rstrip().endswith("?")
