# Stage 0: Foundation

**Goal:** Create the monorepo, tooling, local infrastructure, CI, and project memory so every later stage starts from a green, documented baseline. No product features in this stage.

**Estimated size:** 3 to 5 days of human time; roughly 8 focused Claude Code sessions.

## Standing rules (read first, applies to every stage)

1. Read `CLAUDE.md` and `docs/PROGRESS.md` before starting (you create both in this stage).
2. Work on one task at a time, in order. After each task: run its **Verify** commands, make a conventional commit, tick the box in `docs/PROGRESS.md`.
3. Items under "Decisions already made" are final. Do not re-open or ask about them.
4. Before using a library API you are unsure about, read its current docs (WebFetch) or its installed type definitions. Do not guess APIs. Let the package manager resolve versions (`pnpm add <pkg>`, `uv add <pkg>`); do not pin versions from memory.
5. Ask the user only when you need: an API key or account action, a manual check on the live LeetCode site, or a product decision not covered here. Otherwise decide, record it in `docs/DECISIONS.md`, and continue.
6. If a task fails after two real attempts, write what you tried to `docs/BLOCKERS.md`, skip to the next independent task, and report it at the end.
7. Never commit secrets, real LeetCode page HTML, or problem statements or editorials copied from LeetCode. All fixtures must be synthetic.
8. Stay inside this stage's scope. Put new ideas in `docs/BACKLOG.md` instead of building them.

## Project context

Aporia is a Chrome extension (Manifest V3) plus a Python backend. On LeetCode it detects when a student is stuck and gives Socratic hints (never the answer). The backend verifies hints by running the student's code against a verified reference solution, and a leak guard checks every reply. A learner model remembers concepts and mistakes.

## Decisions already made

- Monorepo: pnpm workspaces + Turborepo. Node 22 (`.nvmrc`), pnpm via corepack.
- Extension: WXT, React, TypeScript (strict), Tailwind, Vitest, Playwright.
- API: Python 3.12 managed with `uv`; FastAPI (async), Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic, Redis, Arq, pytest, ruff, pyright.
- Database image: `pgvector/pgvector:pg16`. Redis 7.
- Shared contract: Pydantic models are the source of truth; FastAPI's OpenAPI is exported and converted to TypeScript with `openapi-typescript`. Zod schemas are used only for runtime validation of messages inside the extension.
- Sandbox: Judge0 CE in Docker Compose under the profile `sandbox` (it is optional until Stage 2).
- Lint/format: ESLint + Prettier (TS), ruff (Python).

## Target repository layout

```
aporia/
  apps/extension/          # WXT app
  apps/api/                # FastAPI app (uv project)
  packages/shared/         # generated API types + shared zod helpers
  evals/                   # promptfoo + python eval scripts (empty for now)
  ml/                      # training code (empty for now)
  knowledge/               # concept notes (empty for now)
  infra/                   # docker-compose.yml, judge0.conf
  docs/                    # PROGRESS.md, ARCHITECTURE.md, DECISIONS.md, BACKLOG.md, BLOCKERS.md
  .github/workflows/ci.yml
  CLAUDE.md
  README.md
  .env.example
```

## Tasks

### 0.1 Repository skeleton
- `git init`, add `.gitignore` (node, python, `.env`, `.venv`, `dist`, `.output`, `.wxt`, `__pycache__`, `*.onnx`, `ml/artifacts`).
- Create root `package.json` (private), `pnpm-workspace.yaml` (`apps/*`, `packages/*`), `turbo.json` with pipelines: `lint`, `typecheck`, `test`, `build`.
- Add `.nvmrc` (22), `.editorconfig`, `.prettierrc`, root `README.md` (one paragraph + "see CLAUDE.md").
- Create empty folders with `.gitkeep`: `evals`, `ml`, `knowledge`, `infra`, `docs`.
- If `stage0.md` to `stage6.md` are present next to the repo (or in the working directory), move them to `docs/stages/` and commit them. Later stages are executed from those files.

**Verify:** `corepack enable && pnpm install` succeeds; `pnpm turbo run lint` runs (it may find no tasks yet).

### 0.2 Extension shell (`apps/extension`)
- Scaffold with WXT's React template: `pnpm dlx wxt@latest init apps/extension --template react --pm pnpm`. If the command is interactive and blocks, scaffold manually instead (`wxt`, `@wxt-dev/module-react`, `react`, `react-dom`, `typescript`, `@types/chrome`).
- Set `"strict": true` in `tsconfig`; forbid `any` via ESLint (`@typescript-eslint/no-explicit-any: error`).
- Add Tailwind (current major version, via its Vite plugin wired through `wxt.config.ts`), Vitest, and a trivial passing test.
- `wxt.config.ts`: set manifest `name: "Aporia"`, `host_permissions: ["https://leetcode.com/*"]`, `permissions: ["storage"]` only. Do not add other permissions.
- Add scripts: `dev`, `build`, `zip`, `lint`, `typecheck`, `test`.

**Verify:** `pnpm --filter extension build && pnpm --filter extension test && pnpm --filter extension typecheck`.

### 0.3 API shell (`apps/api`)
- `cd apps && uv init api --python 3.12`, then add dependencies: `fastapi uvicorn[standard] pydantic-settings sqlalchemy[asyncio] asyncpg alembic redis arq httpx` and dev: `pytest pytest-asyncio ruff pyright`.
- Package layout: `app/main.py`, `app/config.py` (pydantic-settings, reads `.env`), `app/db.py` (async engine/session), `app/api/health.py`, `tests/`.
- `GET /healthz` returns `{"status": "ok"}`; `GET /readyz` checks Postgres and Redis connectivity.
- `app/export_openapi.py` writes `openapi.json` to the path given in argv[1].
- Configure ruff (line length 100) and pyright (basic mode, `app` included).
- Alembic: async-aware `env.py`; first migration `0001_extensions` runs `CREATE EXTENSION IF NOT EXISTS vector;`.

**Verify:** `cd apps/api && uv run ruff check . && uv run pyright && uv run pytest`.

### 0.4 Local infrastructure (`infra/docker-compose.yml`)
- Services: `postgres` (pgvector/pgvector:pg16, port 5432, volume, healthcheck), `redis` (redis:7, port 6379).
- Profile `sandbox`: `judge0-server`, `judge0-workers`, `judge0-db` (postgres:16), `judge0-redis` (redis:7). Fetch Judge0's official `judge0.conf` defaults from its repository docs and save as `infra/judge0.conf`. `judge0-server` and workers need `privileged: true`.
- Judge0 CE v1.13.x requires cgroup v1. If it fails to start on this host, do not fight it: note the cgroup limitation in `docs/DECISIONS.md` and leave the profile in place. Stage 2 uses a `SandboxRunner` interface so a different runner can be substituted.
- `.env.example` with: `DATABASE_URL`, `REDIS_URL`, `JUDGE0_URL`, `APORIA_ENV`, `APORIA_MODEL_FAST`, `APORIA_MODEL_STRONG`, `APORIA_MODEL_JUDGE`, `APORIA_LLM_MOCK`, `LANGFUSE_*` (blank). For the model variables, add a comment that the user must fill them with provider model strings.

**Verify:** `docker compose -f infra/docker-compose.yml up -d postgres redis`, then `cd apps/api && uv run alembic upgrade head` succeeds and `uv run uvicorn app.main:app` serves `/readyz` with `ok`.

### 0.5 Shared contract package (`packages/shared`)
- Add `openapi-typescript`. Script `pnpm gen:api` at the repo root runs: `uv --project apps/api run python -m app.export_openapi packages/shared/openapi.json && pnpm --filter shared exec openapi-typescript openapi.json -o src/api.d.ts`.
- `packages/shared/src/index.ts` re-exports the generated types. Add a CI check later (task 0.6) that fails if generated files are out of date.
- Add `zod` to the extension; no schemas yet.

**Verify:** `pnpm gen:api` produces `src/api.d.ts` containing the `/healthz` path; `pnpm --filter shared typecheck` passes.

### 0.6 Continuous integration (`.github/workflows/ci.yml`)
- Job `web`: checkout, setup pnpm + Node 22 with cache, `pnpm install --frozen-lockfile`, `pnpm turbo run lint typecheck test build`.
- Job `api`: services `postgres` (pgvector image) and `redis`; setup uv; `uv sync`; `ruff check`, `pyright`, `alembic upgrade head`, `pytest`.
- Job `contract`: run `pnpm gen:api` and fail if `git diff --exit-code packages/shared` shows changes.
- Cache dependencies; run on pull requests and pushes to `main`.

**Verify:** validate the YAML with `actionlint` if available (otherwise careful read-through); every command in the workflow runs locally.

### 0.7 Project memory and documentation
Write these files; keep each under 150 lines (add them to git ignore):
- `CLAUDE.md` (content below).
- `docs/PROGRESS.md`: a checklist of every task in stages 0 to 6 (task IDs only, unchecked), with Stage 0 ticked as you go.
- `docs/ARCHITECTURE.md`: components and data flow (browser: MAIN-world bridge, content script + Shadow DOM UI, service worker, IndexedDB; backend: gateway, orchestrator, retrieval, execution, LLM gateway, leak guard; data: Postgres+pgvector, Redis, Judge0; offline: ML + evals).
- `docs/DECISIONS.md`: the "Decisions already made" list above, with dates.
- `docs/BACKLOG.md`: user stories (as a student stuck on a problem, I want...), 8 to 10 of them, ordered.
- `docs/BLOCKERS.md`: empty with a header.

`CLAUDE.md` must contain:
```
# Aporia
Proactive Socratic study companion for LeetCode (Chrome MV3 extension + FastAPI backend).

## Layout
(see repository layout in docs/ARCHITECTURE.md)
Stage plans: `docs/stages/stage0.md` to `stage6.md`. Work on one stage at a time.

## Commands
- Install: `pnpm install` ; `cd apps/api && uv sync`
- Dev extension: `pnpm --filter extension dev`
- Dev API: `docker compose -f infra/docker-compose.yml up -d postgres redis` then `cd apps/api && uv run uvicorn app.main:app --reload`
- Checks: `pnpm turbo run lint typecheck test build` ; `cd apps/api && uv run ruff check . && uv run pyright && uv run pytest`
- Regenerate API types: `pnpm gen:api`

## Conventions
- TypeScript strict, no `any`. Python fully typed, async, Pydantic v2.
- Pydantic models are the source of truth; never hand-edit `packages/shared/src/api.d.ts`.
- All LeetCode selectors, URLs and GraphQL queries live in `apps/extension/src/lib/leetcode/constants.ts`.
- Prompts are files in `apps/api/app/prompts/` with a version suffix; never inline long prompts in code.
- Pure logic (ladder, stuck rules, shrinker, BKT, fusion) must have unit tests.
- Conventional commits; one task per commit.

## Product invariants (never violate)
1. Aporia never outputs solution code or the exact fix, at any hint level.
2. Student code is never logged at INFO level or stored in analytics events.
3. The extension only reads the user's own page and never auto-submits.
4. No real LeetCode HTML, problem statements, or editorials are committed. Fixtures are synthetic.
5. Failing safe: if the leak guard or sandbox errors, return a deterministic safe hint, not a raw model reply.
```

**Verify:** all files exist; `docs/PROGRESS.md` lists every task ID from stage 0 to 6 (read the other stage files if present; otherwise list the stage headings only).

## Acceptance criteria (all must be true)

- [ ] `pnpm install && pnpm turbo run lint typecheck test build` passes from a clean clone.
- [ ] `cd apps/api && uv run ruff check . && uv run pyright && uv run pytest` passes.
- [ ] `docker compose -f infra/docker-compose.yml up -d postgres redis` works and `alembic upgrade head` creates the `vector` extension.
- [ ] `curl localhost:8000/readyz` returns ok with the stack running.
- [ ] `pnpm gen:api` is reproducible (no diff on a second run).
- [ ] CI workflow exists and mirrors the local commands.
- [ ] `CLAUDE.md`, `docs/*.md`, and `.env.example` exist; no secrets are committed.

## Out of scope

Any LeetCode-specific code, LLM calls, database tables beyond the extension migration, the UI beyond the WXT template, shadcn/ui setup (Stage 1).

## Hand-off notes

At the end, append to `docs/PROGRESS.md`: commands that were verified, anything skipped (for example Judge0 on cgroup v2), and the exact Node/Python/package-manager versions in use.
