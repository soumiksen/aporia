# Architecture

## Repository layout
```
aporia/
  apps/extension/          # WXT app (MV3, React, Tailwind)
  apps/api/                # FastAPI app (uv project)
  packages/shared/         # generated API types + shared zod helpers
  evals/                   # promptfoo + python eval scripts
  ml/                      # training code
  knowledge/               # concept notes
  infra/                   # docker-compose.yml, judge0.conf
  docs/                    # PROGRESS, ARCHITECTURE, DECISIONS, BACKLOG, BLOCKERS, stages/
  .github/workflows/ci.yml
```

## Browser (Chrome MV3, WXT)
- **LeetCode page**: Monaco editor, GraphQL and submit API (read-only, the user's own session).
- **MAIN-world bridge**: runs in the page's JS world; reads the Monaco model and observes
  fetch/XHR verdicts; talks to the content script via `window.postMessage`.
- **Content script + Shadow DOM UI**: React panel (mascot) isolated from LeetCode CSS.
- **Service worker**: API client, device id, system-idle relay (`chrome.idle`, 60 s), consent and
  the telemetry queue (flush every 30 s or 20 events, retry with backoff). The stuck detector
  itself runs in the content script as pure rules (`src/lib/stuck/`) fed by bridge messages,
  page visibility and the idle state; cooldown/snooze/per-problem opt-out live in
  `chrome.storage.local`.
- **IndexedDB (Dexie)**: local-first learner data: mistakes, settings, cached hints.

## Backend (Python 3.12, FastAPI)
- **Gateway**: JWT auth, Redis rate limiting, Pydantic v2 validation, SSE streaming.
- **Orchestrator**: hint-level state machine (ladder L1-L4), learner-model read/write, context
  assembly, versioned prompt files.
- **Retrieval**: Postgres FTS + pgvector (HNSW), fused by RRF, cross-encoder rerank.
- **Execution**: Arq worker on Redis; differential tests and a failing-input shrinker against
  Judge0 through a `SandboxRunner` interface.
- **LLM gateway**: LiteLLM routing/fallback/caching; structured output via Instructor.
- **Leak guard**: deterministic heuristics (code blocks, AST similarity to the reference, correctness
  claims, expected-output reveal), then an LLM judge, rewrite once, else a deterministic safe hint.
- **Grounding** (`app/grounding/`): failing-case finder, shrinker, context builder; see
  `docs/GROUNDING.md`. 12 s budget, falls back to prompt-only hints.
- **Events** (`POST /v1/events`): opt-in, strict allowlist, stored in `events`; optional PostHog
  forwarding (Arq cron) and Sentry error tracking, both off unless configured.

## Data
- **Postgres 16 + pgvector**: problems, concepts, attempts, hints, mistakes, mastery, events.
- **Redis 7**: rate limits, Arq queue, caches.
- **Judge0 CE** (compose profile `sandbox`): isolated code execution, no network.

## Offline
- **ML**: synthetic leaky/safe data, DeBERTa-v3 fine-tune, ONNX export (`ml/`).
- **Evals**: promptfoo + pytest red-team, retrieval precision, hint rubric (`evals/`, CI).

## Data flow (one help cycle)
1. Page opened -> slug and tags loaded. 2. Bridge observes code and verdicts.
3. Service worker detects stuck. 4. Orchestrator picks the rung (ladder + mastery).
5. Grounding: minimal failing case (Judge0) + retrieved notes + similar mistakes.
6. LLM draft -> leak guard (rewrite or safe hint). 7. Hint streams over SSE to the panel.
8. Student acts; events return. 9. Learner model and review schedule updated.

## Contract
Pydantic models -> FastAPI OpenAPI -> `pnpm gen:api` -> `packages/shared/src/api.d.ts`.
Zod is used only for runtime validation of messages inside the extension.
