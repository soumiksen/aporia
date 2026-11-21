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

## Stage 2 implementation decisions (2026-11-18)
- **Ladder skipping:** the stage text ("never skip more than one level above level_reached + 1") is
  ambiguous. Implemented the conservative reading: a request is capped at `level_reached + 1`
  (no skipped rungs). Asking for a lower level re-serves it. Auto-escalation after 3 failed
  attempts raises the level to `level_reached + 1`. Table-driven tests pin this.
- **Contract additions:** `HintRequest.failed_attempts` (failed runs since the last hint, counted by
  the extension) and `last_verdict`; `done.supported` (false: prompt-only); `POST
  /v1/hint/{id}/rating` for the "Not helpful" link (writes `hints.rating`, owner-checked).
- **Statement text is never stored.** The `problems` table has no statement column (privacy), so
  the build job receives the problem context in its Arq job arguments (transient, in Redis).
- **Reference verification:** 400 cases requested (200 tiny, 150 small, 50 large), invalid ones are
  dropped, and at least 300 valid cases must agree. Brute-force timeouts are tolerated only on
  `large` cases. `gen` and `validate` also run in the sandbox. Infrastructure failures (LLM or
  sandbox down) are not stored as a permanent `failed`.
- **Harness extension:** a fourth harness mode `gen` (the module's `gen`/`validate` are untrusted
  code too), per-case timeouts use `setitimer` (float seconds) instead of `alarm`.
- **Unordered comparison** sorts every list recursively by canonical JSON.
- **Guard failure policy:** a failure of the *first draft generation* is an `error` event (an LLM
  outage must not look like a normal hint). Any failure of the guard, or of the regeneration after
  a leak, returns the deterministic safe hint. Replies are never returned unchecked while the
  guard is on. `X-Aporia-Disable-Guard: 1` works only when `APORIA_ENV=eval`.
- **Heuristics:** AST similarity threshold 0.6 (`SIMILARITY_THRESHOLD`), shingle size 4 with at
  least 8 shingles for containment; fenced or unfenced code over 3 lines is blocked at levels 1-3.
  Hedged mentions ("I cannot say whether your code is correct") are not treated as assertions.
- **Judge:** `partial` and `full` severity both count as leaks even if `leaks` is false.
- **Sandbox on this host:** Judge0 (Docker Desktop, cgroup v2) resolves the Python language id and
  accepts `enable_network: false`, but cannot run submissions (status 13 "Internal Error"). Reference
  pipeline and harness are tested with a real subprocess runner that exists **only in tests**
  (`tests/support/subprocess_runner.py`, trusted synthetic code, not a sandbox). The Judge0
  integration test skips with that reason.
- **Eval device state:** each red-team request uses a fresh device and the ladder state is
  pre-seeded in Redis so requests for levels 3 and 4 are not capped to level 1.
- **Scoring independence:** the deterministic score reuses the AST tools with a stricter threshold
  (0.5) plus a verbatim reference-line overlap signal, and a separate LLM judge prompt; a reply
  counts as leaked if either flags it.
- The Stage 1 prompt `hint_v0` was replaced by `hint_l1_v1` ... `hint_l4_v1`.

## Stage 3 implementation decisions (2026-11-20)
- **Grounded semantics:** `done.grounded` is true only when a real failing case was found and is
  cited by the hint. "No failing input found" (prompt tells the model not to claim correctness) and
  every error path (timeout, sandbox error, no reference, non-Python) report `grounded: false`.
- **Sandbox error vs. invariant 5:** Stage 3 says grounding errors continue prompt-only. The reply
  is still generated through the leak guard, so it is never a raw model reply; guard errors still
  return the deterministic safe hint.
- **Grounding runs at every level** (so the failure kind and the attempts row are recorded), but
  level 1 prompts reveal nothing from it. Levels 2-4 may show the minimal input and the student's
  actual output. The expected output and the reference code reach only the guard (`GuardFacts`).
- **Shrinker validation:** the reference module's `validate(args)` runs in the sandbox (new harness
  mode `validate`), so the shrinker takes an optional async `validate_batch`. Candidate batches are
  8 (not larger) so the 150-evaluation budget is spent on the most aggressive candidates first.
  Integers shrink with geometrically decreasing steps and ties prefer smaller magnitude.
  "Still fails" requires the same failure kind, so a wrong answer never morphs into a crash.
- **Expected-output check** (`reveals_expected_output`): a cue phrase ("expected", "should return",
  "the answer is" ...) followed by the expected value, or a long structured value appearing outside
  the input quote. Deliberately conservative: false positives cost only a rewrite or safe hint.
- Prompt versions: `hint_l*_v2` (with `{grounding}`) are the default via `APORIA_PROMPT_VERSION`;
  v1 stays for evals. `guard_judge_v2` receives the failing case.
- `attempts` rows are written for every hint request (hash of the code, verdict, failing input
  only). `POST /v1/hints/{id}/rating` is added next to the Stage 2 route in task 3.6.
- **Error tracking (3.8):** Sentry is on only when `SENTRY_DSN` (API) or `VITE_SENTRY_DSN`
  (extension build) is set; it is not tied to the telemetry consent card, because the stage plan
  gates it on the DSN alone and reports are scrubbed (request bodies dropped, fields `code`,
  `content_text`, `student_message` and identifying headers filtered, no stack-frame variables).
  Free-text exception messages are not scrubbed, so code must never be put in an exception message.
  The extension reports background and options-page errors only (content-script errors run in the
  page and are not collected). The background worker is a module worker so the Sentry SDK ships as
  a lazily loaded chunk that DSN-less builds never load.


## Stage 4: learner model, semantic search and RAG
- **Learner data is server-side, keyed by the anonymous device hash** (this differs from the earlier
  local-first plan, because retrieval needs pgvector). `concept_mastery` holds concept ids and BKT
  numbers; `mistakes` holds a concept id, one sentence and an embedding; `problem_summaries` holds
  the slug, tags, an own-words summary and an embedding. **No code and no statement text** is
  stored in any of them or in `events`. To be restated in `docs/PRIVACY.md` (Stage 6).
- `POST /v1/attempts` (slug + verdict, no code) and the hint endpoint feed BKT. The attempts call is
  functional, not telemetry, so it is not gated by the consent card (it carries no code and is
  keyed by the same device id as every hint request). A failed observation is counted once per
  distinct code hash, so asking for the same hint repeatedly does not drive mastery down.
- **Migration is `0005_rag_learner`** (the plan says 0004, which `events` already took). The `tsv`
  generated columns exist only in the migration; the models omit them so they run on the SQLite
  unit-test database, and full-text SQL uses `literal_column("<table>.tsv")`.
- **EMBED_DIM = 1536** everywhere. Provider vectors with fewer dimensions are zero-padded (cosine
  unchanged); more dimensions is an error. The dev setup uses Ollama `nomic-embed-text` (768
  dimensions, padded).
- Full-text queries are `websearch_to_tsquery` over the query words joined with `or`, because a
  student-style sentence rarely contains every term and the default AND would match nothing.
- RRF ties break by the best rank any list gave, then first appearance. Retrieval metrics rank
  **concepts** (chunks of one note count once).
- Mistake descriptions are generated **deterministically** from the failure kind and the minimal
  failing input (`describe_failure`), not by an LLM: it cannot leak code and needs no model call.
  One mistake is stored against the problem's primary (first) concept.
- Summaries that copy 8 consecutive words of the statement are rejected like an invalid slug and
  are never stored. After two invalid answers the summary is stored with no concepts and
  `needs_review = true`.
- Prompts `hint_l*_v3` are the default (`APORIA_PROMPT_VERSION`); `guard_judge_v3` adds the level 4
  "must not be the student's problem or a re-skin" rule. The guard also gets two deterministic
  checks: `quotes_source` and `restates_problem`.
- The reranker is **off** and not installed by default (the `rerank` uv group downloads torch and a
  2 GB model); retrieval metrics for `hybrid_rerank` stay empty until it is enabled.
- The retrieval labels are drafts (`status = needs_human_label`); the report says so until every
  row is `labeled`.
