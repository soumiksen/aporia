# Guard comparison: prompted vs classifier-only vs cascade

> **TODO: no numbers yet.** This file is filled in by `evals/guard_compare/run.py` once the leak
> classifier has been trained (`ml/modal_train.py`), exported (`ml/export/export_onnx.py`) and
> served from `APORIA_CLASSIFIER_DIR`. Nothing below is an estimate; until then there is no result
> to interpret.

How to produce it (after training):

```
cd apps/api
APORIA_CLASSIFIER_DIR=../../ml/artifacts/onnx \
  uv run python ../../evals/guard_compare/run.py
```

It evaluates the three guard modes on (a) the held-out test split of
`ml/data/leak_dataset.jsonl` and (b) the replies from the Stage 2 red-team runs, and reports
recall, false-positive rate, precision, p50/p95 latency and the estimated cost per 1,000 checks.
