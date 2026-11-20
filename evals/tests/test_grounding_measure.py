from grounding.measure import measure, wrong_solutions
from redteam.loaders import load_problems


async def test_every_synthetic_problem_has_a_plausible_wrong_solution() -> None:
    assert set(wrong_solutions()) == set(load_problems())


async def test_grounding_finds_a_small_failing_input_for_every_synthetic_problem() -> None:
    report = await measure()
    assert report["problems"] == len(load_problems())
    assert report["success_rate"] == 1.0, report["rows"]
    for row in report["rows"]:
        assert row["kind"] == "wrong_answer"
        assert row["input_size"] <= 30  # shrunk: a handful of characters of JSON, not a big array
        assert row["seconds"] < 12  # inside the total grounding budget
