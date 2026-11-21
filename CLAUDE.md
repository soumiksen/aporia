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
- Knowledge base: `cd apps/api && uv run python ../../scripts/validate_knowledge.py` ; ingest: `uv run python -m app.rag.ingest` (see docs/RAG.md)
- Offline evals tests: `pnpm eval:test` ; red-team run (real keys, costs money): `pnpm eval:redteam` then `pnpm eval:gate`
- Extension e2e: `pnpm --filter extension e2e` (needs `npx playwright install chromium` once)

## Conventions
- TypeScript strict, no `any`. Python fully typed, async, Pydantic v2.
- Pydantic models are the source of truth; never hand-edit `packages/shared/src/api.d.ts`.
- All LeetCode selectors, URLs and GraphQL queries live in `apps/extension/src/lib/leetcode/constants.ts`.
- Prompts are files in `apps/api/app/prompts/` with a version suffix; never inline long prompts in code.
- Pure logic (ladder, stuck rules, shrinker, BKT, fusion) must have unit tests.
- Untrusted code runs only through a `SandboxRunner` (Judge0), never in the API process.
- Every reply passes the leak guard before it is shown; a guard error returns a safe hint, and a
  sandbox (grounding) error continues prompt-only, still guarded.
- Conventional commits; one task per commit.

## Product invariants (never violate)
1. Aporia never outputs solution code or the exact fix, at any hint level.
2. Student code is never logged at INFO level or stored in analytics events. Telemetry is opt-in,
   allowlisted (no code, no problem text), and error reports are scrubbed. `attempts` stores a
   hash of the code, never the code.
3. The extension only reads the user's own page and never auto-submits.
4. No real LeetCode HTML, problem statements, or editorials are committed. Fixtures are synthetic.
5. Failing safe: if the leak guard errors, return a deterministic safe hint, not a raw model reply.
   If grounding (the sandbox) errors, continue prompt-only: the reply is still generated and guarded.
6. The expected output and the reference code never reach the hint generator, only the guard.
7. Learner data (mastery, mistakes, problem summaries) is keyed by the device hash and holds no
   code and no problem statement text. Study notes are background, never quoted as the answer.
