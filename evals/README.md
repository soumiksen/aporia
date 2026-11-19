# Evals

## Red-team suite (`evals/redteam/`)

64 attack cases (8 categories x 8) against 10 invented problems, each with a hand-written reference
solution that the pipeline's own verifier accepts. Each case is sent to the API twice, with the leak
guard on and off, and every reply is scored by an independent deterministic check plus an LLM judge.

Files: `cases.yaml`, `problems/*.json`, `run.py` (source of truth), `score.py`, `summary.py`,
`gate.py`, `baseline.json`, `results/` (git-ignored output).

### Run it (costs real LLM calls)
1. Start Postgres and Redis and migrate: see `docs/MANUAL_TESTS.md` for port overrides.
   `cd apps/api && uv run alembic upgrade head`
2. Start the API in eval mode with real models (never mock):
   ```
   cd apps/api
   APORIA_ENV=eval APORIA_MODEL_FAST=<model> APORIA_MODEL_JUDGE=<model> \
     uv run uvicorn app.main:app --port 8001
   ```
   plus the provider API key your LiteLLM model string needs.
3. In another shell, with the same `DATABASE_URL`, `REDIS_URL` and model variables:
   `pnpm eval:redteam --api http://localhost:8001`
   Add `--no-llm-judge` for deterministic scoring only, or `--limit 8` for a quick smoke run.
4. `pnpm eval:gate` exits non-zero if the guard-on leak rate is above `baseline.json`.

`X-Aporia-Disable-Guard` only works when the API runs with `APORIA_ENV=eval`; `run.py` checks this
before it starts and aborts otherwise.

### Offline tests (no network, no keys)
`pnpm eval:test` covers scoring, summary, gate, the case/problem files, and runs the whole suite
against the real FastAPI app with a scripted model.

### promptfoo
`evals/promptfooconfig.yaml` exposes the same cases through a custom provider for the promptfoo UI
(`npx promptfoo eval -c evals/promptfooconfig.yaml`, then `npx promptfoo view`). It needs the API
running as above. `run.py` stays the source of truth for the gate.

### CI
Not part of default CI because it costs money. The manually triggered workflow
`.github/workflows/redteam.yml` runs it and needs repository secrets.
