# Progress

Only `stage0.md` existed when this file was written, so stages 1 to 6 list headings only.
Replace each heading with its task IDs when those stage files are added to `docs/stages/`.

## Stage 0: Foundation
- [x] 0.1 Repository skeleton
- [x] 0.2 Extension shell
- [x] 0.3 API shell
- [x] 0.4 Local infrastructure
- [x] 0.5 Shared contract package
- [x] 0.6 Continuous integration
- [x] 0.7 Project memory and documentation

## Stage 1: Walking skeleton
- [x] 1.1 Constants and types
- [x] 1.2 MAIN-world bridge
- [x] 1.3 Isolated content script, SPA navigation, problem metadata
- [x] 1.4 Shadow DOM panel and mascot
- [x] 1.5 Service worker: device id, API client, streaming
- [x] 1.6 API: hint endpoint and LLM gateway
- [x] 1.7 Tracing
- [x] 1.8 Wire the UI to the API
- [x] 1.9 End-to-end tests with synthetic fixtures
- [x] 1.10 Manual checklist for the user (written; **the user still has to run it**)

## Stage 2: Hint ladder and leak guard
- [x] 2.1 Database models and migration
- [x] 2.2 Sandbox runner
- [x] 2.3 Reference-solution pipeline
- [x] 2.4 Hint ladder state machine
- [x] 2.5 Deterministic safe hints
- [x] 2.6 Leak guard v1 (prompted)
- [x] 2.7 Red-team suite (built and tested offline; **the user still has to run `pnpm eval:redteam` with real keys**)
- [x] 2.8 Extension: ladder UI

## Stage 3: Execution-grounded hints and stuck detection
- [x] 3.1 Batch execution
- [x] 3.2 Failing-case finder
- [x] 3.3 Shrinker
- [x] 3.4 Grounded hint generation
- [x] 3.5 Stuck detector (extension)
- [x] 3.6 Nudge UI
- [x] 3.7 Consent and events
- [x] 3.8 Error tracking
- [x] 3.9 Optional: PostHog forwarding
- [x] 3.10 Documentation

## Stage 4: Learner model, semantic search, and RAG
- [x] 4.1 Schema
- [x] 4.2 Concept taxonomy
- [x] 4.3 Concept notes (original content)
- [x] 4.4 Embeddings and ingestion
- [x] 4.5 Problem summaries and tagging
- [x] 4.6 Hybrid retrieval
- [x] 4.7 Learner model
- [x] 4.8 Use retrieval and learner data in hints
- [x] 4.9 Retrieval evaluation

## Stage 5: Fine-tuning, performance, observability
- [x] 5.1 Synthetic problem set
- [x] 5.2 Leak dataset builder
- [x] 5.3 Training code
- [ ] 5.4 ONNX export and serving wrapper
- [ ] 5.5 Cascade guard
- [ ] 5.6 Guard comparison
- [ ] 5.7 Routing, caching, and cost tracking
- [ ] 5.8 Observability
- [ ] 5.9 CI additions

## Stage 6: User study, hardening, launch
- [ ] (task IDs to be added from stage6.md)

## Stage 0 hand-off notes

### Verified commands
- `pnpm install && pnpm turbo run lint typecheck test build`: passes (5 tasks).
- `cd apps/api && uv run ruff check . && uv run pyright && uv run pytest`: passes.
- `docker compose -f infra/docker-compose.yml up -d postgres redis` (host ports 5433/6380 via
  `APORIA_POSTGRES_PORT`/`APORIA_REDIS_PORT`), then `uv run alembic upgrade head`: `vector`
  extension created; `/readyz` returned `{"status":"ok","postgres":"ok","redis":"ok"}`.
- `pnpm gen:api`: `api.d.ts` contains `/healthz`; second run produces no diff;
  `pnpm --filter shared typecheck` passes.
- `.github/workflows/ci.yml`: `actionlint` clean; local equivalents of each step pass.

### Skipped or not verified
- **Judge0 (profile `sandbox`)**: starts but test submission returns "Internal Error"
  (Docker Desktop / cgroup v2). See `docs/DECISIONS.md`. Profile left in place.
- CI has not run on GitHub (no remote yet).
- Verified on Node 26 locally; CI uses Node 22 from `.nvmrc`.
- Playwright is listed in the stack but not installed yet (no e2e tests in Stage 0).
- Prettier is installed with config but not wired into a `lint` task; ESLint covers the extension.
- A host Postgres on 5432 conflicts with the compose default port (see DECISIONS).

### Versions
- Node v26.0.0 local (target 22), pnpm 12.21.0, uv 0.13.9, Python 3.12.13
- wxt ^0.21.3, react ^19.2.4, tailwindcss ^4.3.5, vitest ^5.1.0, zod ^4.6.7, typescript ^5.9.3
- fastapi 0.163.2, pydantic 2.14.3, sqlalchemy 2.1.9, alembic 1.20.1, ruff 0.17.5,
  pyright 1.1.414, pytest 9.2.0

## Stage 1 hand-off notes

### Verified commands (2026-11-17)
- `pnpm turbo run lint typecheck test build`: passes (extension: 40 Vitest tests).
- `pnpm --filter extension e2e`: 4 Playwright tests pass (headless Chromium, synthetic fixture).
- `cd apps/api && uv run ruff check . && uv run pyright && uv run pytest`: passes (19 tests, mock
  mode, no network or keys).
- Real API run with Docker Redis: SSE tokens then `done`; missing device header gives 400; the
  31st request in a minute gives 429.

### Verified only against synthetic fixtures (not the live site)
- Monaco access (a fake `window.monaco`), verdict parsing (synthetic check JSON), GraphQL
  metadata (synthetic response), SPA navigation (`history.pushState` in the fixture), and the
  streamed hint (mock API). No real LLM call has been made; LiteLLM is tested with a stub.

### Rive status
- SVG fallback only. No `.riv` file exists in `apps/extension/src/assets/`, so `Mascot` is an
  inline SVG with `mood` and `size` props and the `@rive-app/*` package is not installed.

### LeetCode assumptions the user must confirm
See the end of `docs/MANUAL_TESTS.md`: URL shapes, GraphQL access and shape, run/submit/check URLs
and `state: "SUCCESS"`, run vs submit inference from `runcode` in the id, `window.monaco`
availability and language ids, and the description fallback selector.

### Notes
- Both content scripts match all of `https://leetcode.com/*` (SPA injection); see DECISIONS.
- Production builds have no API host permission yet; only dev builds include the API origin.
  Set the production API URL and permission before release (Stage 6).
- Judge0 remains unresolved on this host (see Stage 0 notes); not needed until Stage 2.
- Not run on GitHub CI yet in this stage; the new `e2e` job is validated with actionlint only.

### Versions added
- extension: @webext-core/messaging, eventsource-parser, zustand, radix-ui, @playwright/test,
  jsdom, @testing-library/*; api: litellm, langfuse (>=4.7,<5), fakeredis (dev).

## Stage 2 hand-off notes

### Verified commands (2026-11-18)
- `pnpm turbo run lint typecheck test build`: passes (extension: 61 Vitest tests).
- `pnpm --filter extension e2e`: 8 Playwright tests pass (multi-level SSE, rating, banner, failed
  attempts, SPA navigation, error state).
- `cd apps/api && uv run ruff check . && uv run pyright && uv run pytest`: 210 passed, 2 skipped
  (Judge0 integration; Postgres round-trip is `-m db`, run separately and passing).
- `pnpm eval:test` (offline evals tests): 37 passed, including a full red-team run through the real
  FastAPI app with a scripted model.
- `alembic upgrade head` -> `0002_core_tables` on Postgres 16 + pgvector; downgrade/upgrade and
  `alembic check` clean.
- `pnpm eval:redteam` plumbing against real Postgres, Redis and HTTP with a canned model: works
  (seeding, eval-mode check, results file, summary table, gate). That run proves nothing about leak
  rates and its result file was deleted.

### Not verified / needs the user
- **First real-model attempt (2026-11-19/20), Gemini free tier:** the key works and a real hint plus
  guard-judge round trip succeeded, but the Google free tier allows only **20 requests per day per
  model** ("generate_content_free_tier_requests, limit: 20"), so the red-team run (about 400+ calls)
  was rate-limited and produced no usable numbers (partial results deleted). It needs a paid tier
  (billing enabled on the Google project) or a provider with higher limits. `.env` has
  `APORIA_LLM_MOCK=0`; for everyday UI testing start the API with `APORIA_LLM_MOCK=1` to avoid
  burning quota. LiteLLM retries (`llm_num_retries`, default 4) cannot help with a daily quota.
- **First real leak rates: not yet measured.** Run `pnpm eval:redteam` with real keys (see
  `evals/README.md`) and share the summary table. Placeholders to fill in once available:
  guard-off leak rate: ____ ; guard-on leak rate: ____ (target 0.0; `baseline.json` is 0.0).
- **Judge0 does not run on this host** (Docker Desktop, cgroup v2): language lookup works, execution
  returns Internal Error. The sandbox integration test is explicitly skipped here. The harness and
  pipeline were verified with a test-only subprocess runner instead. Reference building in the
  worker needs Judge0 on a cgroup-v1 Linux host.
- No real LLM was called for hints, the reference pipeline or the guard judge (all scripted or
  mocked). Prompts have not been tuned against a live model.
- promptfoo config (`evals/promptfooconfig.yaml`) is written but was not run (needs network and
  `npx promptfoo`).
- The new CI jobs and `redteam.yml` passed `actionlint` only; nothing has run on GitHub.

### Sandbox runner in use
`Judge0Runner` (production) / `FakeRunner` and a test-only `SubprocessRunner` (tests).

### Problem types marked unsupported (`supported = false`, prompt-only hints)
Any problem whose parameters or return type mention `ListNode`, `TreeNode` or `Node`; design-class
problems (`classname`/`methods`/`systemdesign` metadata); manual-judge problems; problems with a
`void` or unknown return type; problems with no method metadata.

### Guard thresholds chosen
`SIMILARITY_THRESHOLD = 0.6` (AST similarity to the reference; 4-token shingles, at least 8 for
containment), fenced/unfenced code over 3 lines blocked at levels 1-3, correctness assertions
blocked at levels 1-3, judge `partial`/`full` count as leaks, one rewrite then safe hint. The
red-team scorer uses a stricter 0.5 plus verbatim reference-line overlap.

### Reference pipeline
At least one synthetic problem is verified through the pipeline in tests (`test_success_first_try`)
and all 10 red-team reference modules pass the same verification (400+ agreeing cases each).

### Contract changes since Stage 1
`HintRequest.failed_attempts`/`last_verdict`, `done.supported`, `POST /v1/hint/{id}/rating`,
`POST /v1/internal/reference/{slug}`. Regenerate with `pnpm gen:api` (done).

## Stage 3 hand-off notes

### Verified commands (2026-11-20)
- `pnpm turbo run lint typecheck test build`: passes (extension: 150 Vitest tests).
- `pnpm --filter extension e2e`: 14 Playwright tests pass (adds nudge Yes / Not now / Never /
  auto-dismiss, consent card, and a canary check that opted-in events carry no code or problem text).
- `cd apps/api && uv run ruff check . && uv run pyright && uv run pytest`: 329 passed, 2 skipped.
- `pnpm eval:test`: 39 passed (adds the grounding measurement test).
- `alembic upgrade head` -> `0004` on Postgres 16, downgrade/upgrade round trip, `alembic check`
  clean; the `-m db` round trip (hints.grounded, events) passes against the container.

### Grounding on the synthetic problem set (offline, real execution)
`uv --directory apps/api run python ../../evals/grounding/measure.py`
- **Success rate: 10 of 10 (100%)**, one plausible wrong student attempt per problem.
- Minimal failing inputs of 3 to 15 JSON characters (for example `[[0, 0, 0], 0]` for the Pair Count
  fixture, which needs exactly three elements).
- **Typical latency: median 0.18 s, max 0.55 s** with the local subprocess runner. This does NOT
  include Judge0 network overhead; the 12 s budget caps it. Real latency on Judge0 is unmeasured
  because Judge0 cannot run on this host (Docker Desktop, cgroup v2).
- Synthetic wrong solutions are plausible but small; real student code has more variety.

### Stuck thresholds in use (`src/lib/stuck/rules.ts`, `policy.ts`)
Stuck if any of: 3+ consecutive failed submissions; same failing verdict and same last testcase
twice in a row; no edits and no runs for 4 minutes (tab visible, system not idle; the clock restarts
when the tab or system becomes active again); fewer than 20 changed characters over 10 minutes after
at least 2 failed runs (and the tracker has observed a full 10 minutes). Cooldown 10 min after any
nudge, snooze 30 min after "Not now" (or the 12 s auto-dismiss), "Never on this problem" persistent.
Evaluated on every signal and every 15 s. "Were you actually stuck?": 30% after a dismissal, once
per page load.

### Data collected for a future learned stuck detector
None yet. Telemetry is opt-in and off by default, there are no real users yet, and the `events` table
only exists since migration 0004. Once people opt in it will hold `stuck_prompt_shown/accepted/
dismissed` (with the rule that fired), `hint_requested`, `hint_rated` and `stuck_label`
(`was_stuck` true/false) events: enough to compare the rules against user labels later. No code or
problem text is ever stored in it.

### Not verified / needs the user
- **Nudge flow on the live site:** run the Stage 3 section of `docs/MANUAL_TESTS.md` (items 24 to
  37). The rules were tested with synthetic fixtures and fake timers only; whether real LeetCode
  run/submit responses match what the detector expects (status messages, `last_testcase`) is
  unconfirmed.
- **`chrome.idle`:** the relay is built and typed but only exercised in unit tests (the e2e browser
  never goes idle). Check items 30 and 31.
- **Real grounding end to end:** needs Judge0 on a cgroup-v1 Linux host plus a real model and a
  verified reference (built by the Arq worker). Everything is tested with the real harness through a
  local subprocess runner and a scripted model.
- **PostHog forwarding** is tested against a mock HTTP transport only (no real PostHog project).
- **Sentry** is tested with a capturing transport only (no real DSN).
- CI jobs (including the longer e2e job) have still not run on GitHub.

### Notes
- New permissions: `idle`. The background worker is now a module worker (lazy Sentry chunk).
- New environment variables: `SENTRY_DSN`, `VITE_SENTRY_DSN`, `POSTHOG_API_KEY`, `POSTHOG_HOST`,
  `GROUNDING_BUDGET_S`, `APORIA_PROMPT_VERSION` (default `v2`; use `v1` to reproduce Stage 2 evals),
  `APORIA_LLM_EXTRA_PARAMS`.
- Red-team results measured on the Stage 2 prompts (v1) are not comparable with v2 prompts; rerun
  the suite with `APORIA_PROMPT_VERSION=v1` for a like-for-like comparison, or re-baseline.


## Stage 4 hand-off notes

### What was built
- Schema (migration `0005_rag_learner`; the plan said 0004, which `events` took), taxonomy (40
  concepts), 40 original notes (`reviewed: false`), embedder + ingestion, problem summaries, hybrid
  retrieval, BKT learner model, mistakes, `POST /v1/attempts`, hint integration (`<notes>`,
  `<past_mistakes>`, `<analogous_problems>`, `done.sources`, "Based on" chips), retrieval eval and a
  hint-quality harness. Design and switches: `docs/RAG.md`.

### Embedding model and reranker (as actually used)
- Embedding model: Ollama `nomic-embed-text` (`APORIA_EMBEDDING_MODEL=ollama/nomic-embed-text`),
  768 dimensions zero-padded to `EMBED_DIM = 1536`. 85 chunks from 40 notes.
- Reranker: **not enabled** (`APORIA_RERANK` unset, the optional `rerank` uv group is declared but
  not installed; it pulls torch and a 2 GB model). `hybrid_rerank` has no numbers yet.

### Retrieval metrics (115 draft queries, labels NOT yet reviewed: provisional)
| mode | P@3 | P@5 | R@5 | MRR | p50 ms | p95 ms |
|---|---|---|---|---|---|---|
| vector | 0.345 | 0.217 | 0.861 | 0.774 | 25 | 33 |
| fts | 0.310 | 0.212 | 0.848 | 0.800 | 4 | 5 |
| hybrid | 0.351 | 0.223 | 0.878 | 0.867 | 7 | 9 |
Hybrid beats either alone on every metric. P@k is capped by queries having only one or two relevant
concepts. Full table: `docs/results/retrieval.md`. **The user must review `pairs.csv` labels** (all
rows are `needs_human_label`) before these are treated as final.

### Hint quality, RAG and memory on/off (30 synthetic cases, 120 replies)
Judge and generator are both the local qwen3.5 9B, so this is weak evidence. Scores are 4.7 to 5.0
in every condition (a ceiling effect) and the differences (<= 0.1) are noise: RAG and memory did not
measurably change quality here. `docs/results/hint_quality.md`. All 30 RAG replies carried sources.

### Verified
- Unit/integration: 398 API tests pass (plus the `-m db` Postgres paths when pointed at the compose
  database), 49 evals tests, 156 extension tests, 14 Playwright e2e tests, lint/typecheck/build.
- Real end to end on the dev stack: a new problem got a worker-written summary (2 valid concepts,
  vector stored, no statement text) and the next hints carried `sources`.

### Not verified / needs the user
- **Notes accuracy review** (40 files) and the retrieval labels: manual checks 38 and 39.
- Learner flows on a live site (accepted-submission reporting, past-mistake recall, BKT updates):
  manual checks 40 to 45. Mistake recall needs Judge0 (a grounded failure), which this Mac lacks.
- **The red-team gate has not been re-run on Stage 4 code.** Notes and past mistakes enter the
  prompt, and one real level-2 hint ("shrink the left side of your current stretch ...") named the
  approach and still passed the local 9B judge. Re-run `pnpm eval:redteam` then `pnpm eval:gate`
  against the new code before relying on the guard numbers.
- Level-4 worked-example "is a new problem" is enforced by a prompt rule, an 8-word statement
  overlap heuristic and the judge; it has not been red-teamed with real models.

### Notes the user flagged as inaccurate
None yet (the notes have not been reviewed).
