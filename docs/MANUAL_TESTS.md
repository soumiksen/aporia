# Manual tests (live LeetCode site)

These checks need the real leetcode.com and cannot be automated or faked. Automated tests only
cover synthetic fixtures, so **nothing below is verified until you run it and record the result.**

## Setup
1. Start the backend:
   ```
   cp .env.example .env     # set APORIA_LLM_MOCK=1 for canned tokens, or set APORIA_MODEL_FAST
   docker compose -f infra/docker-compose.yml up -d postgres redis
   cd apps/api && uv run uvicorn app.main:app --reload --port 8000
   ```
   (If your host already uses 5432/6379, set `APORIA_POSTGRES_PORT`/`APORIA_REDIS_PORT` and the
   matching `DATABASE_URL`/`REDIS_URL`.) For a real model, put a provider model string in
   `APORIA_MODEL_FAST` and the provider key in your environment (for example the variable your
   LiteLLM provider expects).
   If something else already uses port 8000 (a 404 from the panel usually means this), pick another
   port, for example `--port 8001`, and use the same port in the next step.
2. Build the dev extension (adds the localhost API permission; match the port above):
   `VITE_API_URL=http://localhost:8000 pnpm --filter extension build:dev`
3. Chrome -> `chrome://extensions` -> enable Developer mode -> Load unpacked ->
   `apps/extension/.output/chrome-mv3-dev`. Sign in to leetcode.com in the same profile.
4. Optional but useful: on the extensions page open the service worker's "Inspect" console.

Helper to paste into the **page** DevTools console (top frame) on any LeetCode tab:
```js
window.addEventListener("message", (e) => {
  if (e.data && e.data.source === "aporia-bridge") console.log("[bridge]", e.data);
});
```

## Checks
| # | Step | Expected | Pass/Fail | Notes |
|---|------|----------|-----------|-------|
| 1 | Open any problem page (for example one you have solved before). Wait ~5 s. | A round rabbit button appears bottom-right. LeetCode's own styling is unchanged. | | |
| 2 | With the helper pasted, type in the code editor. | `[bridge]` lines with `type: "code"`, your code and a language id (note the exact id, e.g. `python` vs `python3`). Fires ~300 ms after you stop typing. | | |
| 3 | Reload, paste the helper, switch the language dropdown. | A new `code` message with the new language and starter code. | | |
| 4 | Click **Run**. | A `[bridge]` line with `type: "verdict"`, `phase: "run"`, a status message, and the output fields. Note any field that is `null` but should have a value. | | |
| 5 | Click **Submit** (use a problem where a wrong submission is fine). | A `verdict` with `phase: "submit"`. Note whether `phase` was inferred correctly (we guess from "runcode" in the check URL). | | |
| 6 | Navigate to another problem **without reloading** (click a problem in the list or "Next"). | The panel's hint clears; no stale text. Typing in the new editor sends `code` messages for the new problem. The next hint is about the new problem. | | |
| 7 | Navigate to the problem list (`/problemset/`). Open the panel. | It says "Open a problem to get started." | | |
| 8 | On a problem page, click the rabbit. | The panel opens and streams a hint (canned in mock mode, or a real Socratic question with a real model). The hint contains no code. | | |
| 9 | Stop the API and click the rabbit again (close and reopen the panel first). | A clear "Could not reach the Aporia server" message with a Try again button. | | |
| 10 | Close the panel while a hint is streaming. | Streaming stops; reopening starts a fresh request. | | |
| 11 | Check the problem metadata: in the service worker or page network tab, find the `graphql` request after opening a problem. | HTTP 200 with `question` data. Note if it is blocked, redirected, or returns a different shape. | | |
| 12 | Press keys (for example `j`, `/`, `?`) while the panel button is focused. | LeetCode shortcuts are not triggered by typing inside the panel. | | |
| 13 | Tab to the rabbit button and press Enter or Space. | The panel opens; focus ring visible. | | |
| 14 | Check API logs while requesting a hint. | No student code appears in the logs. | | |

## LeetCode assumptions to confirm (all in `apps/extension/src/lib/leetcode/constants.ts`)
- Problem URLs look like `/problems/<slug>/` and `/problems/<slug>/description/`.
- GraphQL endpoint `https://leetcode.com/graphql` accepts the `question(titleSlug)` query with
  the user's cookies from a content script (no CSRF header needed).
- Run uses `/problems/<slug>/interpret_solution/`, submit uses `/problems/<slug>/submit/`, and
  results come from polling `/submissions/detail/<id>/check/` with `state: "SUCCESS"`.
- `window.monaco` is reachable from the page's main world and `monaco.editor.getEditors()` works.
- The description fallback selector `[data-track-load="description_content"]` (only used when
  GraphQL fails).

Record anything that fails in `docs/BLOCKERS.md`.

---

# Stage 2 manual checks (ladder, guard, red-team)

Needs a real model: set `APORIA_MODEL_FAST` and `APORIA_MODEL_JUDGE` (provider model strings) and
that provider's API key in the API's environment, and do **not** set `APORIA_LLM_MOCK`. Postgres
(migrated: `cd apps/api && uv run alembic upgrade head`) and Redis must be running; use the same
port overrides as above. Rebuild the dev extension after pulling (`build:dev`) and reload it.

| # | Step | Expected | Pass/Fail | Notes |
|---|------|----------|-----------|-------|
| 15 | Click the rabbit on a problem you know. | An **L1 Nudge** badge and a single guiding question (not the same sentence for different problems). | | |
| 16 | Type a few words in "Tell Aporia what you are stuck on" and click **Need a bigger hint**. | Badge becomes **L2**; the hint reflects your note. The box clears. | | |
| 17 | Keep clicking **Need a bigger hint**. | L3 (approach in words, no code) then L4 (a *different* analogous problem). The button is disabled at L4. | | |
| 18 | At every level, read the reply. | No solution code and no exact fix for your problem. Report any that leak. | | |
| 19 | Paste a correct solution, type "is this correct?", ask for a hint. | The reply declines to confirm and asks about a small input instead. | | |
| 20 | Fail a submission 3 times, then ask for a hint. | The hint is one level higher than the last one (auto-escalation). | | |
| 21 | Open a problem with a linked list or tree in the signature (`ListNode`, `TreeNode`). | After the hint arrives a note says Aporia cannot run your code on this problem yet. | | |
| 22 | Click **Not helpful**. | "Thanks for the feedback". In Postgres, `select rating from hints order by created_at desc limit 1` is 1. | | |
| 23 | With the API running, check `reference_solutions`. | After the first hint on a supported problem, a row appears (`verified` or `failed`) once the Arq worker has run. **Judge0 does not run on Docker Desktop (cgroup v2)**, so use a Linux host or expect `infrastructure_error` in the worker log. | | |

To build references you must also run the worker: `cd apps/api && uv run arq app.worker.WorkerSettings`
(needs Judge0 reachable at `JUDGE0_URL`, plus `APORIA_MODEL_STRONG`).

## Red-team run (costs real LLM calls)
Follow `evals/README.md`, then **share the printed summary table** (guard-off vs guard-on leak
rate per category). Run `pnpm eval:gate` to check against `evals/redteam/baseline.json`.

