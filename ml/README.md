# ml/: leak classifier (Stage 5)

A DeBERTa-v3 binary classifier (`leak` vs `safe`) that the cascade guard runs before the LLM judge.

| Step | Command | Where |
|---|---|---|
| 1. problems | `ml/data/synth_problems.py` | local, LLM calls |
| 2. references | `ml/data/build_references.py` | local, needs Judge0 |
| 3. dataset | `ml/data/build_leak_dataset.py`, `validate_dataset.py` | local, LLM calls |
| 4. smoke test | `cd ml && uv run python train/train_classifier.py --smoke` | CPU, about a minute |
| 5. train | `modal run ml/modal_train.py` (see the file's header) | **Modal GPU, you run it** |
| 6. export | `cd ml && uv run python export/export_onnx.py ...` | local CPU |
| 7. serve | `APORIA_CLASSIFIER_DIR=... ` in the API | `app/guard/classifier.py` |
| 8. compare | `evals/guard_compare/run.py` | local, after training |

The heavy dependencies (torch, transformers, optimum) live in `ml/pyproject.toml` (`cd ml && uv sync`),
not in `apps/api`. The pure-Python parts (metrics, thresholds, dataset builder, formatter) are tested
from the API environment: `cd apps/api && uv run pytest ../../ml -q`.

## Where artifacts live
Weights are never committed (`ml/artifacts/`, `*.onnx`, `*.safetensors` are git-ignored). Trained
artifacts sit on the Modal volume `aporia-leak-classifier` under `/artifacts/classifier`; the
exported ONNX bundle (`model.onnx`, `tokenizer.json`, `model_card.json`) is what the API loads from
`APORIA_CLASSIFIER_DIR`. To share it with other machines, upload that directory somewhere private
(a private Hugging Face repo or an object-store bundle) and set `APORIA_CLASSIFIER_URL`;
`scripts/fetch_classifier.sh` downloads and unpacks it. Record the location you chose here.

## Honesty note
No result in this repository comes from a real training run until you run step 5. The smoke run uses
templated text and its numbers mean nothing.
