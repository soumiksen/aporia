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
