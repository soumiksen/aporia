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

---

# Stage 3 manual checks (nudge, consent, grounding)

Rebuild and reload the dev extension (`VITE_API_URL=... pnpm --filter extension build:dev`). The
manifest now also requests the `idle` permission, so Chrome may ask you to re-approve it.

| # | Step | Expected | Pass/Fail | Notes |
|---|------|----------|-----------|-------|
| 24 | Open any problem and fail a submission 3 times in a row (use a problem where wrong submissions are fine). | The rabbit turns attentive (wide eyes, a small bounce) and a bubble says "Stuck? Want a nudge?" with Yes / Not now / Never on this problem. No hint opens by itself. | | |
| 25 | Click **Yes**. | The panel opens and streams a level-1 hint. | | |
| 26 | Trigger the nudge again within 10 minutes (fail 3 more times). | No bubble during the 10-minute cooldown. | | |
| 27 | After a bubble appears, do nothing for 12 seconds. | It disappears by itself and counts as "Not now" (30-minute snooze). | | |
| 28 | Click **Not now**, reload the page, fail 3 more times. | No bubble for 30 minutes (the snooze is remembered). | | |
| 29 | Click **Never on this problem**, reload, fail 3 times. | No bubble on that problem, ever. Another problem can still nudge you (after the cooldown). | | |
| 30 | Open a problem, stop typing and running for 4 minutes with the tab visible. | The bubble appears (inactivity). Switching to another tab and back restarts the 4-minute clock. | | |
| 31 | Leave the computer idle (no keyboard or mouse) for several minutes, with the tab visible. | No bubble while the system is idle. | | |
| 32 | Turn on "reduce motion" in macOS Accessibility settings and trigger a nudge. | The bubble appears but the mascot does not bounce. | | |
| 33 | After dismissing a few nudges, watch for "Were you actually stuck?". | Appears now and then (about 30% of dismissals), at most once per page load. | | |
| 34 | Open the panel for the first time. | A card asks "Share anonymous usage events to improve Aporia?". Telemetry stays off until you press **Allow**. The same switch is under the extension's options page. | | |
| 35 | With telemetry off, use the extension for a few minutes and check the API log or `select count(*) from events`. | No events arrive. | | |
| 36 | Press **Allow**, request a hint, rate it with 👍/👎, wait a minute. | `select type, slug, props from events order by id desc limit 10` shows `hint_requested`, `hint_rated`, etc. No code or problem text anywhere in those rows. | | |
| 37 | With a **real model and Judge0** (Linux host, see Stage 2 notes), submit a wrong solution and ask for a level-2 hint. | The hint refers to a specific small input and what your code returns for it, asks you to trace it, and never states the correct output or the fix. `select grounded, failure_kind from hints order by created_at desc limit 1` shows `t | wrong_answer`. | | |

Record any failures in `docs/BLOCKERS.md`.


---

# Stage 4 manual checks (notes, memory, labels)

Start the API with `APORIA_EMBEDDING_MODEL` set (Ollama: `ollama pull nomic-embed-text`, then
`APORIA_EMBEDDING_MODEL=ollama/nomic-embed-text`), run `cd apps/api && uv run alembic upgrade head`
and `uv run python -m app.rag.ingest`, and start the Arq worker (`uv run arq app.worker.WorkerSettings`).
Rebuild and reload the extension.

| # | Step | Expected | Pass/Fail | Notes |
|---|------|----------|-----------|-------|
| 38 | **Review the notes.** Read `knowledge/notes/*.md` (40 files). Fix anything wrong, then `cd apps/api && uv run python ../../scripts/mark_reviewed.py <slug> ...` (or `--list` to see progress). | Every note you checked says `reviewed: true`. Tell me which ones were inaccurate. | | |
| 39 | **Review the retrieval labels.** Open `evals/retrieval/pairs.csv` (115 draft queries). Correct `relevant_slugs` and set `status` to `labeled`, then `uv run python ../../evals/retrieval/run.py`. | `docs/results/retrieval.md` no longer says "Provisional". | | |
| 40 | Open a problem you have never opened, request a hint, wait ~30 s. | `select slug, concepts, needs_review from problem_summaries;` has a row with 1 to 3 concepts. The summary is in different words from the statement and has no examples. | | |
| 41 | Request a level-2 hint on that problem. | The panel shows small "Based on" chips (concept and section). The hint uses them as background and does not quote them. | | |
| 42 | With Judge0 working (Linux), fail a problem with a wrong answer, ask for a hint, then open a different problem with the same kind of bug and ask again. | `select description from mistakes;` shows a one-sentence description with no code. The second hint may say "last time you had trouble with ...", at most once. | | |
| 43 | Submit an accepted solution to a problem you failed earlier. | `select concept_slug, p_known, n_obs from concept_mastery;` shows mastery rising; that problem's mistakes show `resolved = true`. | | |
| 44 | Ask for a level-4 hint (after 1 to 3). | A worked example of a **new** small problem on the same ideas; it is not your problem renamed. | | |
| 45 | `psql` check: `select count(*) from problem_summaries where summary ilike '%' || '<a distinctive phrase from a statement>' || '%';` | 0. No statement text is stored. | | |

Record any failures in `docs/BLOCKERS.md`.

---

# Stage 5 manual checks (classifier, routing, observability)

| # | Step | Expected | Pass/Fail | Notes |
|---|------|----------|-----------|-------|
| 46 | **Build the data** (see `ml/data/README.md`): `synth_problems.py --count 150 --yes`, `build_references.py` (needs Judge0 on a Linux host), `build_leak_dataset.py --yes`, then `validate_dataset.py`. | The validator prints `0 problem(s)` with at least 3,000 records. Tell me the counts. | | |
| 47 | **Train on Modal** (needs a Modal account): follow the header of `ml/modal_train.py` (`modal run ml/modal_train.py`), then download the artifacts. | `model_card.json` exists with `t_low`, `t_high` and test metrics. Share it. | | |
| 48 | Export: `cd ml && uv run python export/export_onnx.py --model-dir artifacts/classifier --data data/leak_dataset.jsonl --out artifacts/onnx` | Prints `export OK` (fp32 and int8 parity within tolerance, 0 formatting mismatches). | | |
| 49 | Serve: set `APORIA_CLASSIFIER_DIR` to that folder, **clear the hint cache** (`redis-cli --scan --pattern 'hintcache:*' \| xargs redis-cli del`) and request a few hints. | `select guard_decision->>'path' from hints order by created_at desc limit 5` shows `classifier_pass` / `judge` / `classifier_block`. | | |
| 50 | Compare the guards: `cd apps/api && APORIA_CLASSIFIER_DIR=../../ml/artifacts/onnx uv run python ../../evals/guard_compare/run.py` | `docs/results/guard.md` is replaced by real tables. Tell me what you see. | | |
| 51 | Re-run the red-team gate with the cascade on: `pnpm eval:redteam --api ...` then `pnpm eval:gate` (see `evals/README.md`). | Gate PASS (guard-on leak rate 0). | | |
| 52 | `docker compose -f infra/docker-compose.yml --profile observability up -d lgtm`, run the API with `OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318`, request hints, open http://localhost:3000 and import `infra/grafana/aporia-dashboard.json`. | Five panels with data; tell me if any looks wrong. | | |
| 53 | Set `APORIA_DAILY_BUDGET_USD=0.0001` with a paid model and request hints. | After the limit, hints are the fixed safe hints and the API log shows "daily LLM budget reached". | | |

Record any failures in `docs/BLOCKERS.md`.
