# Decisions

## Fixed at project start (2026-11-17)
- Monorepo: pnpm workspaces + Turborepo. Node 22 (`.nvmrc`), pnpm via corepack.
- Extension: WXT, React, TypeScript (strict), Tailwind, Vitest, Playwright.
- API: Python 3.12 via `uv`; FastAPI (async), Pydantic v2, SQLAlchemy 2 (async, asyncpg),
  Alembic, Redis, Arq, pytest, ruff, pyright.
- Database image `pgvector/pgvector:pg16`; Redis 7.
- Shared contract: Pydantic is the source of truth; OpenAPI -> TypeScript via
  `openapi-typescript`; Zod only for runtime message validation in the extension.
- Sandbox: Judge0 CE in Docker Compose profile `sandbox` (optional until Stage 2).
- Lint/format: ESLint + Prettier (TS), ruff (Python).

## Stage 0 implementation decisions (2026-11-17)
- Repo root is the existing `Aporia/` directory (not a nested `aporia/`).
- Docs in task 0.7 are committed. The stage text says "add them to git ignore"; read as
  "add to git", since later stages rely on them.
- `packageManager` is set in root `package.json` (pnpm 12.21.0) so CI's `pnpm/action-setup`
  and corepack resolve it without a version input.
- WXT template's demo content script (matched google.com) was removed so the manifest only
  has `https://leetcode.com/*` and `storage`. Content script arrives in Stage 1.
- `pnpm gen:api` uses `uv --directory apps/api` (`--project` alone does not change cwd).
- Compose host ports are overridable (`APORIA_POSTGRES_PORT`, `APORIA_REDIS_PORT`) because a
  host Postgres on 5432 silently shadowed the container during verification.
- Judge0 ports/passwords in `infra/judge0.conf` are throwaway dev values.
- **Judge0 on this host (Docker Desktop, macOS, cgroup v2):** containers start, but a test
  submission returns status 13 "Internal Error" (isolate cannot run). Profile left in place;
  Stage 2 uses a `SandboxRunner` interface so another runner (or a Linux cgroup-v1 host)
  can be used.
- Local Node is v26 (`.nvmrc` and CI use 22); local checks passed on 26 only.

## Stage 1 implementation decisions (2026-11-17)
- WXT `srcDir` is `src` so entrypoints live in `src/entrypoints/` as the stage plan states.
- Both content scripts match `https://leetcode.com/*` (not only `/problems/*`). LeetCode is a
  SPA: a script scoped to problem URLs would not be injected when the student navigates from the
  problem list. The isolated script filters by URL with `MatchPattern` and `wxt:locationchange`.
- The bridge protocol map has two extra messages beyond `getHint`/`getDeviceId`: `cancelHint`
  (abort) and `hintEvent` (service worker -> tab stream relay).
- Verdicts are only emitted from "check" responses with `state === "SUCCESS"`. Run vs submit is
  inferred from the check URL (`runcode` in the id). Unverified against the live site.
- e2e mocks `POST /v1/hint` with a small Node SSE server (`e2e/mock-api.ts`, port 8765) instead
  of `page.route`: the request is made by the service worker, which `page.route` does not see.
  The dev build reads `VITE_API_URL` at build time and adds that origin to `host_permissions`
  (development mode only). The fixture page, GraphQL and run/check calls are still mocked with
  `context.route`.
- The hint endpoint fails open on a Redis error in the rate limiter (logged, request allowed);
  `/readyz` reports Redis health. `code` size is enforced in the endpoint (not Pydantic) so it
  returns 413 as specified instead of 422.
- The API serves level 1 behavior for any `level` 1..4 and reports `done.level = 1`.
- Student code is kept out of Langfuse traces by default by turning off LiteLLM message logging
  (`litellm.turn_off_message_logging`) unless `APORIA_TRACE_CODE=1`. This also hides the model
  reply in traces until that flag is on.
- shadcn's CLI misresolved WXT's `@/` alias (wrote to `apps/src` and added a stray `cn` package);
  the Button was moved by hand and the import fixed. Future `shadcn add` runs need the same check.
- Tailwind rem values are compiled to px by a small PostCSS plugin in `wxt.config.ts`, so the
  host page's `html` font-size cannot rescale the panel (setting font-size on a container does
  not change rem).
