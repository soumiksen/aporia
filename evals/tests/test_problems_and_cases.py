from collections import Counter

import pytest
from app.reference.pipeline import Analysis, verify_module
from app.reference.supported import is_supported
from app.sandbox.harness import run_cases
from tests.support.subprocess_runner import SubprocessRunner

from redteam.loaders import case_request, load_cases, load_problems

PROBLEMS = load_problems()
CASES = load_cases()
CATEGORIES = {
    "direct_ask", "confirmation", "role_play", "encoding",
    "incremental", "injection", "reveal_tests", "pseudocode",
}  # fmt: skip


def test_there_are_8_to_10_synthetic_problems() -> None:
    assert 8 <= len(PROBLEMS) <= 10
    for slug, p in PROBLEMS.items():
        assert p["slug"] == slug
        for key in (
            "title",
            "difficulty",
            "tags",
            "content_text",
            "meta",
            "examples",
            "comparison",
            "reference_module",
        ):
            assert key in p, (slug, key)
        assert is_supported(p["meta"])[0], slug
        assert "leetcode" not in p["content_text"].lower()


@pytest.mark.parametrize("slug", sorted(PROBLEMS))
async def test_reference_modules_are_verified_by_the_pipeline(slug: str) -> None:
    """Hand-written references must pass the same check as generated ones."""
    p = PROBLEMS[slug]
    analysis = Analysis(
        examples=p["examples"], method=p["meta"]["name"], comparison=p["comparison"]
    )
    result = await verify_module(p["reference_module"], analysis, SubprocessRunner())
    assert result.ok, result.report
    assert len(result.cases) >= 300


def test_at_least_60_cases_and_6_per_category() -> None:
    assert len(CASES) >= 60
    counts = Counter(c["category"] for c in CASES)
    assert set(counts) == CATEGORIES
    assert all(n >= 6 for n in counts.values()), counts


def test_case_fields_are_valid_and_ids_unique() -> None:
    ids = [c["id"] for c in CASES]
    assert len(ids) == len(set(ids))
    for c in CASES:
        for key in ("id", "category", "problem_slug", "level", "student_message", "code", "notes"):
            assert key in c, (c["id"], key)
        assert c["problem_slug"] in PROBLEMS and 1 <= c["level"] <= 4
        assert c["student_message"].strip() and c["code"].strip()
        body = case_request(c, PROBLEMS[c["problem_slug"]])
        assert body["problem"]["slug"] == c["problem_slug"] and body["level"] == c["level"]


def test_levels_are_spread_and_all_problems_are_used() -> None:
    assert {c["level"] for c in CASES} == {1, 2, 3, 4}
    assert {c["problem_slug"] for c in CASES} == set(PROBLEMS)


def test_injection_cases_carry_the_payload() -> None:
    inj = [c for c in CASES if c["category"] == "injection"]
    in_text = [c for c in inj if c.get("problem_text")]
    in_code = [c for c in inj if "#" in c["code"]]
    assert len(in_text) >= 3 and len(in_code) >= 3
    body = case_request(in_text[0], PROBLEMS[in_text[0]["problem_slug"]])
    assert body["problem"]["content_text"] == in_text[0]["problem_text"]


@pytest.mark.parametrize(
    "case", [c for c in CASES if c["category"] == "confirmation"], ids=lambda c: c["id"]
)
async def test_pasted_solutions_in_confirmation_cases_are_really_correct(case) -> None:
    """A "is this correct?" attack is only meaningful if the pasted code is correct."""
    p = PROBLEMS[case["problem_slug"]]
    out = await run_cases(
        SubprocessRunner(),
        mode="student",
        source=case["code"],
        method=p["meta"]["name"],
        cases=[e["args"] for e in p["examples"]],
    )
    assert [r.out for r in out] == [e["expected"] for e in p["examples"]], out
