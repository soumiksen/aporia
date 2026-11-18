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
