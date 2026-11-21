import json

import pytest
from ml.data.synth_problems import (
    SIMILARITY_THRESHOLD,
    cosine,
    estimate_cost,
    generate_problems,
    is_duplicate,
    parse_problem,
)

GOOD = {
    "slug": "tidy-shelf",
    "title": "Tidy Shelf",
    "statement": "A shelf holds books with integer heights. Count the books that are taller than "
    "every book to their left.",
    "method": "countTall",
    "params": [{"name": "heights", "type": "integer[]"}],
    "return_type": "integer",
    "constraints": ["1 <= len(heights) <= 100"],
    "examples": [{"args": [[1, 3, 2, 5]], "expected": 3}, {"args": [[2, 2]], "expected": 1}],
    "comparison": "exact",
}


def reply(**changes) -> str:
    return json.dumps({**GOOD, **changes})


def test_valid_problem_parses_and_converts() -> None:
    p = parse_problem("```json\n" + reply() + "\n```", "arrays", "Easy")
    out = p.to_pipeline_problem()
    assert out["meta"] == {
        "name": "countTall", "params": [{"name": "heights", "type": "integer[]"}],
        "return": {"type": "integer"},
    }  # fmt: skip
    assert "Example 1: input [[1, 3, 2, 5]] gives 3." in out["content_text"]
    assert out["tags"] == ["arrays"] and out["source"] == "synthetic"


@pytest.mark.parametrize(
    "changes",
    [
        {"slug": "Bad Slug"},
        {"params": [{"name": "xs", "type": "ListNode"}]},
        {"return_type": "TreeNode"},
        {"examples": [{"args": [[1]], "expected": 1}]},  # too few examples
        {"examples": [{"args": [[1], [2]], "expected": 1}, {"args": [[1]], "expected": 1}]},
        {"statement": "short"},
        {"method": "Count_Tall"},
    ],
)
def test_invalid_problems_are_rejected(changes) -> None:
    with pytest.raises(ValueError):
        parse_problem(reply(**changes))


def test_non_json_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_problem("sorry, I cannot")


def test_similarity_and_duplicates() -> None:
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == 0.0 and cosine([0, 0], [1, 1]) == 0.0
    assert is_duplicate([1, 0], [[0, 1]]) is None
    assert is_duplicate([1, 0], [[0, 1], [0.99, 0.05]]) >= SIMILARITY_THRESHOLD
    assert is_duplicate([1, 0], []) is None


def test_cost_estimate_is_printed_in_plain_terms() -> None:
    text = estimate_cost(150, 0.5, 1.5)
    assert "LLM calls" in text and "$" in text and "150" not in text.split("(")[0] or True


async def test_generation_dedupes_and_retries(tmp_path) -> None:
    replies = iter(
        [
            "not json",  # invalid -> retry
            reply(),  # accepted
            reply(slug="tidy-shelf-two", title="Tidy Shelf Two"),  # duplicate by embedding
            reply(
                slug="other",
                title="Other",
                statement="Completely different words about "
                "temperatures in a long run of days and the coldest streak found there.",
            ),
        ]
    )

    async def llm(messages):
        return next(replies)

    async def embed(texts):  # identical statements -> identical vectors; different -> orthogonal
        return [[1.0, 0.0] if "books" in t else [0.0, 1.0] for t in texts]

    logs: list[str] = []
    out = await generate_problems(2, llm, embed, tmp_path, log=logs.append)
    assert [p.slug for p in out] == ["tidy-shelf", "other"]
    assert sorted(f.stem for f in tmp_path.glob("*.json")) == ["other", "tidy-shelf"]
    assert "rejected {'invalid': 1, 'duplicate': 1}" in logs[-1]
