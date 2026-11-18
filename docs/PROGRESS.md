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
- [ ] 1.7 Tracing
- [ ] 1.8 Wire the UI to the API
- [ ] 1.9 End-to-end tests with synthetic fixtures
- [ ] 1.10 Manual checklist for the user

## Stage 2: Hint ladder and leak guard
- [ ] (task IDs to be added from stage2.md)

## Stage 3: Execution-grounded hints and stuck detection
- [ ] (task IDs to be added from stage3.md)

## Stage 4: Learner model, semantic search, and RAG
- [ ] (task IDs to be added from stage4.md)

## Stage 5: Fine-tuning, performance, observability
- [ ] (task IDs to be added from stage5.md)

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
