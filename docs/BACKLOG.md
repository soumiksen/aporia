# Backlog (ordered)

1. As a student stuck on a problem, I want to click Aporia and get a one-line nudge so that I
   re-read the problem without being told the answer.
2. As a student stuck on a problem, I want a hint that points at the concept or failing case so
   that I can find my own bug.
3. As a student stuck on a problem, I want to ask for the next hint level so that I control how
   much help I get.
4. As a student stuck on a problem, I want hints that never contain solution code so that I
   still do the thinking.
5. As a student stuck on a problem, I want a hint built from the smallest input my code fails
   on so that the hint is specific and true.
6. As a student stuck on a problem, I want Aporia to offer help only after I am truly stuck, with
   a "not now" button, so that it does not interrupt my flow.
7. As a student stuck on a problem, I want Aporia to remember my recurring mistakes so that it
   can say "you hit this same off-by-one last week".
8. As a student stuck on a problem, I want a worked example of a similar problem so that I learn
   the idea without seeing this problem solved.
9. As a student stuck on a problem, I want my code and history to stay on my device by default
   so that I can trust the tool.
10. As a student stuck on a problem, I want to see which concepts I am weak at so that I know what
    to practise next.

## Ideas parked during Stage 1
- Mascot animation with Rive once a `.riv` asset is provided (props: mood, size).
- Production API URL, host permission, and CORS policy for released builds.
- Show the hint level and a "next hint" button in the panel (levels 2 to 4 come in Stage 2).
- Surface the captured language id mapping (monaco ids vs LeetCode `python3`) in the request.
- Dark mode for the panel (theme variables already live on `:host`).

## Ideas parked during Stage 2
- Execution-grounded hints: student mode in the harness already exists; failing-case search and
  shrinking are Stage 3.
- Show the student's own `attempts` history (the table exists but is not written yet).
- Per-level model routing (fast model for L1-L2, strong for L3-L4) once Stage 5 adds routing.
- Replace the test-only subprocess runner with a Judge0 on a cgroup-v1 Linux host for CI.
- Surface "guard rewrote this hint" to the student only as telemetry, never in the panel.
- A classifier-first guard (Stage 5) to cut judge latency and cost.

