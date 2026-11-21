# Leak dataset

Generated files are git-ignored (`ml/data/problems/*.json`, `references/*.json`,
`leak_dataset.jsonl`). Nothing here is scraped: problems are invented by an LLM
(`synth_problems.py`, prompt `ml/prompts/synth_problem_v1.md`), checked against the Stage 2
reference pipeline (`build_references.py`), and the replies are generated or come from our own
red-team runs.

## Pipeline (you run the LLM-heavy steps; they cost money or local GPU time)
```
cd apps/api
uv run python ../../ml/data/synth_problems.py --limit 3            # quick check
uv run python ../../ml/data/synth_problems.py --count 150 --yes    # ~150 problems
uv run python ../../ml/data/build_references.py                    # needs Judge0 (Linux host)
uv run python ../../ml/data/build_leak_dataset.py --yes            # ~48 calls per problem
uv run python ../../ml/data/validate_dataset.py                    # hard checks on the real file
```

## Record format (`leak_dataset.jsonl`)
`{id, problem_slug, level, reply, label, source, split}`: `label` is 1 for a leak and 0 for safe;
`source` is `safe`, `hardneg`, `leaky` or `redteam`; `split` is `train`, `val` or `test`, assigned
**by problem** (70/15/15), so no problem appears in two splits. Classes are balanced 50/50 inside
every (split, level) cell. The classifier input is built from the record plus the problem's concept
summary and reference solution by `app/guard/classifier_format.py`.

## Counts
**No full dataset has been built yet.** The builder was run once on a single problem with the
smallest settings to check it end to end (28 records, 1 problem, not enough to train on). Record
the real counts here after your first full run:

| | |
|---|---|
| verified problems | _TODO_ |
| records (train / val / test) | _TODO_ |
| leak share | _TODO_ (target 50%) |
| red-team records kept | _TODO_ |

## Label quality
Leaky replies are labeled by construction (the model was told to leak) and filtered for obvious
refusals and missing code. Safe replies must pass the deterministic guard. Red-team replies are
kept only where the deterministic similarity check and the LLM judge agree. Expect some label
noise; the validation set is where you would spot-check it.

`smoke_dataset.py` builds a **templated** 200-record set that exists only to prove the training
code runs. It is never used for results.
