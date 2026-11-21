# Stage 5: Fine-tuning, performance, and observability

**Goal:** Add the advanced ML component and production-grade engineering. Train a leak classifier, export it to ONNX, build a cascade guard (classifier first, LLM judge for uncertain cases), compare it rigorously with the prompted guard, add model routing and caching, and add metrics dashboards.

**Prerequisite:** Stage 4 acceptance criteria all pass.

## Standing rules (read first)

1. Read `CLAUDE.md` and `docs/PROGRESS.md` before starting.
2. One task at a time, in order. After each task: run its **Verify** commands, make a conventional commit, tick the box in `docs/PROGRESS.md`.
3. "Decisions already made" are final.
4. Before using a library API you are unsure about (transformers, optimum, onnxruntime, Modal, LiteLLM Router, OpenTelemetry), read its docs or installed types. Do not guess.
5. Ask the user only for: API keys/accounts, running GPU jobs, manual checks, or uncovered product decisions.
6. After two failed attempts at a task, log it in `docs/BLOCKERS.md` and move on.
7. Never commit secrets, model weights, or copied LeetCode content. Training data must be synthetic or generated from original problems.
8. Out-of-scope ideas go to `docs/BACKLOG.md`.

## Decisions already made

- **Training data uses original synthetic problems**, not scraped LeetCode problems. Generate about 150 invented problems in classic categories (arrays, strings, hashing, two pointers, windows, binary search, stacks, intervals, simple DP, greedy), each verified through the Stage 2 reference pipeline. This avoids bulk-collecting LeetCode content.
- Classifier: `microsoft/deberta-v3-base` fine-tuned for binary classification (`leak` vs `safe`). A LoRA fine-tune of a small LLM is a stretch goal, not part of this stage.
- Classifier input text format: `[LEVEL] {level} [PROBLEM] {concept summary} [REFERENCE] {reference solution, truncated} [REPLY] {reply}`, truncated to 512 tokens with the reply prioritized (truncate the reference first).
- Splits are **grouped by problem** (no problem appears in more than one split): 70% train, 15% validation, 15% test.
- Primary metric: **recall at a false-positive rate of at most 5%**, because a missed leak is worse than a blocked good hint. Also report precision, F1, ROC-AUC, and PR-AUC.
- Cascade thresholds `t_low` and `t_high` are chosen on the validation set and stored in `model_card.json`: below `t_low` pass; above `t_high` block and rewrite; between them, call the LLM judge.
- GPU training runs on Modal (the user runs it). You must **not** attempt full training locally. Local CPU is for a smoke test only.
- Inference: ONNX Runtime on CPU with dynamic int8 quantization, verified against the fp32 model.
- Model routing: small model for levels 1 and 2, strong model for levels 3 and 4 and for the judge. Models come from env vars `APORIA_MODEL_FAST`, `APORIA_MODEL_STRONG`, `APORIA_MODEL_JUDGE`.

## Tasks

### 5.1 Synthetic problem set
- `ml/data/synth_problems.py`: prompt the LLM (versioned prompt `ml/prompts/synth_problem_v1.md`) to produce original problems as JSON `{slug, title, statement, method, params, constraints, examples, comparison}`. Deduplicate by embedding similarity (reject pairs above a threshold). Save to `ml/data/problems/*.json`.
- `ml/data/build_references.py`: run each through `build_reference` (Stage 2). Keep only `verified` problems; log the verification rate.
- This costs LLM calls: add a `--limit` flag and a cost estimate printed before running; **ask the user to run it** at full size.

**Verify:** unit tests with a mocked LLM for schema validation and dedupe; run with `--limit 3` if keys exist.

### 5.2 Leak dataset builder
- `ml/data/build_leak_dataset.py` writes `ml/data/leak_dataset.jsonl`, one record per `{id, problem_slug, level, reply, label, source, split}`. Sources:
  1. **safe**: Socratic replies at each level from the strong model (4 per problem-level).
  2. **leaky**: replies the model is instructed to make leaky in varied ways: full solution code, partial code containing the key line, step-by-step pseudocode of the exact algorithm, confirmation of a pasted correct solution, solution in another language, solution described in prose with exact steps.
  3. **red-team**: replies from the Stage 2 red-team runs with the guard disabled, labeled by the deterministic similarity check plus the LLM judge (keep only agreement cases).
  4. **hard negatives**: safe replies that mention data structures, complexity, or short non-solution snippets.
- Balance classes (target 50/50 at the full-data level), keep per-level coverage, and assign splits by problem. Print label and per-level distributions.
- Target at least 3,000 records. Record counts in `ml/data/README.md`.

**Verify:** unit tests for split-by-problem (no overlap), label balance, and the input formatter. A script `ml/data/validate_dataset.py` runs these checks on the real file.

### 5.3 Training code
- `ml/train/train_classifier.py` using `transformers.Trainer`: `max_length=512`, learning rate `2e-5`, 3 epochs, batch size 16, weight decay 0.01, warmup 10%, fp16 when a GPU is present, early stopping on validation recall@FPR≤5%. Class weights if imbalanced. Log to Weights & Biases when `WANDB_API_KEY` is set.
- `ml/train/metrics.py`: pure functions for recall at fixed FPR, threshold selection, ROC-AUC, PR-AUC (unit tested on small hand-made arrays).
- `ml/train/thresholds.py`: compute `t_low` (highest threshold with validation recall ≥ 0.99) and `t_high` (lowest threshold with validation precision ≥ 0.95); write `model_card.json` with metrics, thresholds, dataset hash, base model, date.
- `--smoke` flag: 50 steps with `microsoft/deberta-v3-xsmall` on 200 records, CPU allowed; must finish in minutes.
- `ml/modal_train.py`: Modal app (check Modal's current docs) with an A10G-class GPU, an image that installs `ml/requirements.txt` (generate it with `uv pip compile` from `ml/requirements.in` so versions are resolved, not recalled), a Volume for data and artifacts, and a `main` entrypoint that trains and uploads artifacts. Include the exact command the user should run in a comment.
- **Stop and tell the user** to run the Modal job (and what the command is). Do not fabricate or estimate results.

**Verify:** `uv run pytest ml` for metrics, thresholds, and formatter; `python ml/train/train_classifier.py --smoke` runs end to end.

### 5.4 ONNX export and serving wrapper
- `ml/export/export_onnx.py`: export with `optimum` (or `torch.onnx` if you find optimum unsuitable; note in DECISIONS), apply dynamic int8 quantization, and verify parity on 200 test records (max absolute logit difference reported; fail above a constant tolerance chosen and justified in the script).
- `apps/api/app/guard/classifier.py`: `LeakClassifier` loading the ONNX model and tokenizer from `APORIA_CLASSIFIER_DIR`, with `predict_proba(texts) -> list[float]`, request batching, and inference timing. Lazy singleton; if the model directory is missing, the cascade falls back to the Stage 2 prompted guard (log once at WARNING).
- Keep model weights out of git (`.gitignore`); document where artifacts live in `ml/README.md` (for example a Hugging Face Hub private repo or Modal Volume) and the download script `scripts/fetch_classifier.sh` reading `APORIA_CLASSIFIER_URL`.

**Verify:** unit tests for the wrapper with a mocked ONNX session; formatter parity test (the API formats input exactly like training).

### 5.5 Cascade guard
- `app/guard/cascade.py`: heuristics (Stage 2) → classifier probability `p` → if `p < t_low` pass; if `p > t_high` leak (rewrite path); else LLM judge. Same policy as before on leaks (rewrite once, then safe hint). Record the path taken (`heuristic|classifier_pass|classifier_block|judge`) in `guard_decision`.
- Config `APORIA_GUARD_MODE` in `{prompted, classifier_only, cascade}` (default `cascade` when the model exists, else `prompted`).

**Verify:** table-driven unit tests for threshold boundaries and path selection with a fake classifier and fake judge.

### 5.6 Guard comparison (`evals/guard_compare/`)
- `run.py`: evaluates the three modes on (a) the held-out test split and (b) the Stage 2 red-team suite. Report per mode: recall, false-positive rate, precision, p50/p95 latency, and estimated cost per 1,000 checks (from LiteLLM response cost for judge calls; classifier cost is compute time only, note the assumption).
- Output `docs/results/guard.md` with one table and two or three sentences of plain interpretation, written only from real numbers. If the numbers are not available yet, leave a clearly marked TODO. **Ask the user** to run it after training.

**Verify:** unit tests for the metric and cost aggregation with canned results.

### 5.7 Routing, caching, and cost tracking
- `app/llm/router.py`: LiteLLM `Router` with model groups `fast`, `strong`, `judge`, per-provider fallbacks configured from env (a comma-separated list of fallback model strings), timeouts, and retries. Select the group by hint level.
- Caching (Redis): embeddings (already in Stage 4), reference artifacts (database), and hint responses keyed by `(slug, level, code_hash, failing_case_hash, prompt_version)` with a 1-hour TTL. Never cache across devices when learner memory was used in the prompt (include `device_hash` in the key in that case).
- `llm_calls` table: `{id, ts, purpose, model, input_tokens, output_tokens, cost_usd, latency_ms, hint_id null}`; record every call through one wrapper. Add a daily budget guard: when the day's `cost_usd` exceeds `APORIA_DAILY_BUDGET_USD`, return safe hints and log at WARNING.

**Verify:** tests for key construction, cache bypass rules, budget guard, and the call-recording wrapper.

### 5.8 Observability
- Add OpenTelemetry (`opentelemetry-instrumentation-fastapi`, `-sqlalchemy`, `-redis`, `-httpx`) enabled only when `OTEL_EXPORTER_OTLP_ENDPOINT` is set.
- Custom metrics: `aporia_hint_latency_seconds` (histogram, labels: level, grounded), `aporia_guard_decisions_total` (labels: path, outcome), `aporia_retrieval_hits_total`, `aporia_llm_cost_usd_total`, `aporia_sandbox_runs_total` (labels: outcome).
- `infra/docker-compose.yml`: profile `observability` running the all-in-one Grafana OTel LGTM image (check its current name and ports in Grafana's docs).
- `infra/grafana/aporia-dashboard.json`: a dashboard with panels for hint latency p50/p95, guard outcomes by path, cost per hour, retrieval hit rate, sandbox failures. If you cannot import-test it, mark it **unverified** in the file's README.

**Verify:** metrics unit tests using an in-memory metric reader; a startup test that confirms OTel is a no-op without the endpoint.

### 5.9 CI additions
- Add the red-team **gate** and a classifier-wrapper test job (mocked) to CI. Keep real-LLM evals in `workflow_dispatch` workflows only.
- Add `docs/results/` index page `docs/RESULTS.md` linking all result tables.

## Acceptance criteria

- [ ] Dataset builder, training code, metrics, export, and wrapper are complete and unit-tested; the smoke training run works.
- [ ] The user has been given the exact command to run the Modal training job; no fabricated metrics appear anywhere.
- [ ] The cascade and prompted guards both work; missing classifier artifacts fall back safely.
- [ ] Router, cache, budget guard, and `llm_calls` recording work and are tested.
- [ ] OTel and metrics are wired and no-op when not configured.
- [ ] `docs/results/guard.md` exists (filled by real numbers once the user runs the comparison, otherwise clearly marked TODO).

## Out of scope

LoRA LLM fine-tuning, knowledge-tracing parameter fitting, FSRS, learned stuck detector (stretch backlog).

## Hand-off notes

Record in `docs/PROGRESS.md`: dataset size and verified-problem count, the metrics and thresholds from `model_card.json` once available, p95 latency of each guard mode, and the artifact location the user chose.
