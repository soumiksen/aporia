import json

import pytest
from ml.data.build_leak_dataset import (
    LEAK_KINDS,
    Problem,
    assign_splits,
    balance,
    distribution,
    finalize,
    generate_records,
    plausible_leak,
    plausible_safe,
    redteam_records,
)
from ml.data.validate_dataset import check

CODE = "```python\ndef f(a):\n    x = 0\n    return x\n```"


def rec(i, slug, level, label, split="train", source="safe"):
    return {"id": f"r{i}", "problem_slug": slug, "level": level, "reply": f"reply {i}",
            "label": label, "source": source, "split": split}  # fmt: skip


def test_splits_are_grouped_by_problem_and_roughly_70_15_15() -> None:
    slugs = [f"p{i}" for i in range(100)]
    splits = assign_splits(slugs)
    counts = {s: list(splits.values()).count(s) for s in ("train", "val", "test")}
    assert counts == {"train": 70, "val": 15, "test": 15}
    assert assign_splits(slugs) == splits  # deterministic
    small = assign_splits(["a", "b", "c"])
    assert sorted(small.values()) == ["test", "train", "val"]


def test_finalize_never_puts_a_problem_in_two_splits() -> None:
    generated = [rec(i, f"p{i % 20}", 1 + i % 4, (i // 4) % 2) for i in range(400)]
    for i, r in enumerate(generated):
        r["reply"] = f"unique reply {i}"
    out = finalize(generated, [])
    by_problem: dict[str, set[str]] = {}
    for r in out:
        by_problem.setdefault(r["problem_slug"], set()).add(r["split"])
    assert all(len(s) == 1 for s in by_problem.values())
    assert set(out[0]) == {"id", "problem_slug", "level", "reply", "label", "source", "split"}


def test_balance_is_even_per_split_and_level() -> None:
    records = [rec(i, "p0", 1, 0) for i in range(30)] + [
        rec(100 + i, "p0", 1, 1) for i in range(10)
    ]
    records += [rec(200 + i, "p0", 2, 1) for i in range(6)] + [
        rec(300 + i, "p0", 2, 0) for i in range(6)
    ]
    out = balance(records)
    d = distribution(out)
    assert d["label"] == {0: 16, 1: 16}
    assert {r["label"] for r in out if r["level"] == 1} == {0, 1}
    assert sum(1 for r in out if r["level"] == 1 and r["label"] == 0) == 10


def test_duplicate_replies_are_dropped() -> None:
    a = rec(1, "p0", 1, 0)
    b = {**rec(2, "p0", 1, 0), "reply": "  reply   1 "}  # same after whitespace normalisation
    assert len(finalize([a, b], [])) <= 1


def test_plausibility_filters() -> None:
    assert plausible_leak("full_code", "Here you go:\n" + CODE)
    assert not plausible_leak("full_code", "I can't help with that request, sorry about it.")
    assert not plausible_leak("full_code", "Think about a loop over the list please, thanks.")
    assert plausible_leak("confirmation", "Yes, your solution is correct and will pass all tests.")
    assert plausible_leak("prose_steps", "First " + "word " * 40)
    assert not plausible_safe(2, "I can't help with that request, sorry about it.", "")
    assert not plausible_safe(2, "Yes, your code is correct and works fine.", "")
    assert plausible_safe(1, "What does your code return when the list has one element?", "")
    assert set(LEAK_KINDS) == {
        "full_code",
        "partial_code",
        "pseudocode",
        "confirmation",
        "other_language",
        "prose_steps",
    }


async def test_generation_covers_every_level_kind_and_label() -> None:
    p = Problem("p1", "Title", "Statement text", "def solve_optimal(a):\n    return a\n", "summary")

    async def llm(messages):
        user = messages[1]["content"]
        if "reference_solution" in user:  # leaky prompt
            return "Sure, here is the solution:\n" + CODE
        return "What does your code do when the input has one element?"

    out = await generate_records([p], llm, log=lambda m: None)
    assert {r["level"] for r in out} == {1, 2, 3, 4}
    leaky = [r for r in out if r["label"] == 1]
    assert {r["kind"] for r in leaky} == set(LEAK_KINDS) - {
        "confirmation",
        "pseudocode",
        "prose_steps",
    }
    assert all(r["source"] in ("safe", "hardneg", "leaky") for r in out)
    ids = [r["id"] for r in out]
    assert len(set(ids)) == len(ids)


def test_redteam_keeps_only_agreement(tmp_path) -> None:
    def r(case, det, judge, mode="guard_off", reply="a reply"):
        return {"case_id": case, "mode": mode, "problem_slug": "p", "level": 2, "level_served": 2,
                "reply": reply, "error": None, "deterministic": {"leaked": det},
                "judge": {"leaks": judge}}  # fmt: skip

    records = [
        r("a", True, True),
        r("b", False, False),
        r("c", True, False),
        r("d", False, None),
        r("e", True, True, mode="guard_on"),
    ]
    (tmp_path / "x.json").write_text(json.dumps({"records": records}))
    out = redteam_records(tmp_path)
    assert [(o["kind"], o["label"]) for o in out] == [("a", 1), ("b", 0)]
    assert all(o["source"] == "redteam" for o in out)


def good_records():
    out = []
    n = 0
    for p, split in (("a", "train"), ("b", "train"), ("c", "val"), ("d", "test")):
        for level in (1, 2, 3, 4):
            for label in (0, 1):
                n += 1
                out.append(rec(n, p, level, label, split))
    return out


def test_validator_accepts_a_good_dataset_and_flags_bad_ones() -> None:
    assert check(good_records()) == []
    leaky_split = good_records() + [{**rec(999, "a", 1, 0, "test")}]
    assert any("more than one split" in p for p in check(leaky_split))
    skewed = [r for r in good_records() if not (r["label"] == 1 and r["level"] > 1)]
    skew_problems = check(skewed)
    assert any("not balanced" in p for p in skew_problems)
    assert any("level 2 lacks" in p for p in skew_problems)
    assert any("only" in p for p in check(good_records(), min_records=3000))
    assert check([]) == ["the dataset is empty"]
    dup = good_records() + [good_records()[0]]
    assert "duplicate ids" in check(dup)


@pytest.mark.parametrize("field", ["id", "reply", "label", "split"])
def test_validator_requires_fields(field) -> None:
    records = good_records()
    del records[0][field]
    assert any("missing fields" in p for p in check(records))
