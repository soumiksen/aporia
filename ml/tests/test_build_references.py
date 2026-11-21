import json

import fake_pipeline
from ml.data.build_references import build_all


async def test_only_verified_problems_are_kept_and_rate_reported(tmp_path, monkeypatch) -> None:
    files = []
    for slug in ("a", "b", "c"):
        f = tmp_path / f"{slug}.json"
        f.write_text(json.dumps({"slug": slug, "title": slug}))
        files.append(f)
    outcomes = {"a": "verified", "b": "failed", "c": "infra"}
    fake_pipeline.install(monkeypatch, outcomes)
    out = tmp_path / "refs"
    stats = await build_all(files, llm=None, runner=None, out_dir=out, log=lambda m: None)
    assert (stats["verified"], stats["failed"], stats["infra_errors"]) == (1, 1, 1)
    assert stats["verification_rate"] == 0.5  # infrastructure errors are not counted
    assert [p.stem for p in out.glob("*.json")] == ["a"]
    kept = json.loads((out / "a.json").read_text())
    assert kept["reference_module"].startswith("def solve_optimal") and kept["slug"] == "a"
