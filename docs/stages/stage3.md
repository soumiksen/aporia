# Stage 3: Execution-grounded hints and stuck detection

**Goal:** Make hints verified and make Aporia proactive. The backend runs the student's code against the verified reference, finds and shrinks a minimal failing input, and grounds the hint in it. The extension detects genuine stuck-ness with transparent rules and offers a nudge without being annoying.

**Prerequisite:** Stage 2 acceptance criteria all pass.

## Standing rules (read first)

1. Read `CLAUDE.md` and `docs/PROGRESS.md` before starting.
2. One task at a time, in order. After each task: run its **Verify** commands, make a conventional commit, tick the box in `docs/PROGRESS.md`.
3. "Decisions already made" are final.
4. Before using a library API you are unsure about, read its docs or installed types. Do not guess.
5. Ask the user only for: API keys/accounts, manual checks, or uncovered product decisions.
6. After two failed attempts at a task, log it in `docs/BLOCKERS.md` and move on.
7. Never commit secrets, real LeetCode HTML, or copied problem text. Fixtures are synthetic.
8. Out-of-scope ideas go to `docs/BACKLOG.md`.

## Decisions already made

- Execution grounding applies only to problems with `supported = true` and a `verified` reference (Stage 2). Everything else keeps working as prompt-only hints.
- Failure kinds: `wrong_answer`, `runtime_error`, `timeout`. A timeout is judged on the `large` size cases with a per-case limit of 2 seconds.
- The shrinker is generic delta debugging over JSON values and uses the reference's `validate(args)` to keep candidates valid. Budget: at most 150 candidate evaluations or 15 seconds, whichever comes first. If the budget is exhausted, use the smallest failing input found so far.
- What each level may reveal from a failing case: L1 nothing specific; L2 may show the minimal failing **input** and the student's **actual output**, never the expected output or the fix; L3 and L4 follow Stage 2 rules plus the L2 allowance.
- Stuck rules are pure functions with a config object, evaluated in the content script. Defaults: stuck if any of: 3 or more consecutive failed submissions; the same verdict and same `lastTestcase` twice in a row; no edits and no runs for 4 minutes while the tab is visible and the system is not idle; fewer than 20 changed characters over 10 minutes after at least 2 failed runs.
- Cooldown after any nudge: 10 minutes. "Not now" snooze: 30 minutes. "Never on this problem" is persistent for the slug. The nudge never opens a full hint on its own; it only shows "Want a nudge?".
- Telemetry is first-party: batched `POST /v1/events` into a Postgres `events` table. Events never contain code or problem text. Telemetry requires explicit opt-in via a first-run consent card (default off). PostHog forwarding is optional (task 3.9).

## Tasks

### 3.1 Batch execution
- Extend `SandboxRunner` usage with `app/sandbox/batch.py`: `run_cases(source, mode, method, cases, per_case_timeout_s) -> list[CaseResult]` that chunks cases into groups of 50 and runs chunks concurrently (limit 4). Reuse the Stage 2 harness.

**Verify:** unit tests with `FakeRunner` (chunking, ordering, partial timeouts).

### 3.2 Failing-case finder
- `app/grounding/finder.py`: `async find_failure(problem, student_code, reference) -> Failure | None`.
  1. Candidate inputs: statement examples, stored `test_cases`, then fresh generator cases for `tiny` and `small` (seeded RNG, 100 cases), then `large` (20 cases) for timeouts.
  2. Run reference (`solve_optimal`) and student on the same inputs. Compare with the stored comparison mode.
  3. Return the first failure by priority: runtime_error and wrong_answer on smaller inputs first; then timeouts.
  - `Failure = {input, expected, actual, kind, trace_summary}`; `trace_summary` is the last line of the exception only, never a full traceback.
- Return `None` when no failure is found. Then the hint says (in the prompt) that no failing case was found, and must not claim the code is correct.

**Verify:** unit tests with scripted runner results covering wrong_answer, runtime_error, timeout, and no failure.

### 3.3 Shrinker
- `app/grounding/shrink.py`: `async shrink(failing_input, still_fails, validate, budget)`.
  - Lists: try removing halves, then quarters, … then single elements (ddmin).
  - Integers: try 0, then halving toward 0, keeping the sign if the problem needs it.
  - Strings: remove chunks, then characters; then simplify characters toward `a`.
  - Nested lists: apply recursively. Dicts: remove keys, shrink values.
  - Reject candidates where `validate(args)` is false. Evaluate candidate batches in parallel through the batch runner and take the first failing, smallest candidate.
- Keep the shrinker generic: `still_fails` and `validate` are injected callables so it can be tested without a sandbox.

**Verify:** property-style unit tests with pure predicates, for example failure when `sum(xs) > 10` must shrink to a minimal list; failure when `len(s) >= 3 and s[0] == s[-1]` must shrink to 3 characters; budget exhaustion returns the best so far.

### 3.4 Grounded hint generation
- `app/grounding/context.py`: build a `GroundingContext` containing the minimal failing input, the student's actual output, the failure kind, and `trace_summary`. The expected output and the reference code are **only** passed to the guard, never to the generator.
- Update level prompts (new versions `hint_l*_v2.md`; keep v1 for evals): instruct the model to guide using the failing input at L2 and above and to ask the student to trace their own code on it; forbid stating the expected output or the fix.
- Update the guard so it also receives the failing case and flags any reply that states the expected output or the fix.
- The endpoint flow: ladder → (execution grounding if available, with a total time budget of 12 s) → generate → guard → stream. If grounding times out or errors, continue prompt-only and set `grounded: false` in the `done` event.
- Add `grounded: bool` and `failure_kind: str|null` to the `done` event and to the `hints` table (migration `0003`).
- Record an `attempts` row per hint request with `code_hash` and the failing-case summary (input only).

**Verify:** tests with mocked runner and LLM: grounded path, timeout fallback, no-failure path, guard catching a reply that reveals the expected output.

### 3.5 Stuck detector (extension)
- `src/lib/stuck/rules.ts`: `evaluateStuck(snapshot, config, now): {stuck: boolean, reason: StuckReason | null}` pure function. `Snapshot` includes: last edit time, last run time, failed submission count, last verdict + testcase, changed characters in rolling windows, tab visibility, system idle flag.
- `src/lib/stuck/tracker.ts`: collects signals from bridge messages (`code`, `verdict`) and the Page Visibility API; keeps rolling windows; supports fake timers in tests.
- System idle: the service worker uses `chrome.idle.setDetectionInterval(60)` and relays state changes to the content script. Add the `idle` permission to the manifest.
- `src/lib/stuck/policy.ts`: cooldown, snooze, per-slug disable stored in `chrome.storage.local`; `shouldPrompt(now, state) -> boolean`.

**Verify:** exhaustive Vitest tests with fake timers for each rule, cooldown, snooze, visibility, and idle.

### 3.6 Nudge UI
- Mascot animation state `attentive` and a small speech bubble "Stuck? Want a nudge?" with buttons **Yes**, **Not now**, **Never on this problem**. **Yes** requests a level-1 hint. The bubble auto-dismisses after 12 seconds (counts as "not now").
- Respect `prefers-reduced-motion`.
- Thumbs up/down on each hint; send rating to `POST /v1/hints/{id}/rating`.
- After a dismissal, with 30% probability and at most once per session, ask "Were you actually stuck?" (Yes/No). This labels data for a future learned detector.

**Verify:** component and e2e tests for each button; a unit test that the bubble never appears during cooldown.

### 3.7 Consent and events
- First-run consent card in the panel and an options page toggle: "Share anonymous usage events to improve Aporia" (default off). No events are queued while off.
- `POST /v1/events` accepts batches (max 50) of `{type, ts, slug?, level?, reason?, rating?, was_stuck?}`; validate with a strict allowlist of event types; reject unknown fields. Table `events(id, device_hash, type, slug, props jsonb, ts)`.
- Extension batches events in the service worker (flush every 30 s or on 20 events; retry with backoff; drop after 3 failures).
- Events: `stuck_prompt_shown`, `stuck_prompt_accepted`, `stuck_prompt_dismissed`, `hint_requested`, `hint_rated`, `stuck_label`.

**Verify:** API tests (allowlist, size limits, rejection of unknown fields); extension tests (no queue when consent is off).

### 3.8 Error tracking
- Add Sentry to the API and the extension, enabled only when a DSN env var is set. Scrub request bodies and any field named `code`, `content_text`, or `student_message` before sending (`before_send`).

**Verify:** unit test that the scrubber removes those fields.

### 3.9 Optional: PostHog forwarding
- If `POSTHOG_API_KEY` is set, the API forwards stored events to PostHog from a background job. Skip entirely if no key is present. Do not block other tasks on this.

### 3.10 Documentation
- `docs/GROUNDING.md`: a short explanation of the pipeline (finder → shrinker → context → guard) with one worked example using a synthetic problem.
- Update `docs/ARCHITECTURE.md` and the privacy statements in `CLAUDE.md` if anything changed.

## Acceptance criteria

- [ ] All unit and e2e tests pass (mock LLM and fake runner; no network).
- [ ] For a synthetic problem with a deliberately buggy student solution, the pipeline returns a minimal failing input (documented in a test fixture).
- [ ] The shrinker meets its property tests and respects the budget.
- [ ] A hint never includes the expected output or the fix (guard test proves rejection).
- [ ] Stuck rules, cooldown, snooze, and consent are covered by tests; nothing is queued without consent.
- [ ] Events and traces contain no code or problem text (test with a canary string).
- [ ] The user has been asked to run `docs/MANUAL_TESTS.md` additions for the nudge flow on the live site.

## Out of scope

Retrieval/RAG, learner model/BKT, classifier training, learned stuck model (stretch).

## Hand-off notes

Record in `docs/PROGRESS.md`: grounding success rate on the synthetic problem set, typical grounding latency, the stuck thresholds in use, and the data collected so far for future learned stuck detection.
