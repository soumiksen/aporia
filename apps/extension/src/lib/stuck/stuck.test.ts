import { describe, expect, it } from "vitest";
import {
  COOLDOWN_MS,
  EMPTY_POLICY,
  SNOOZE_MS,
  disableSlug,
  loadPolicy,
  recordNudgeShown,
  savePolicy,
  shouldPrompt,
  snooze,
  type StorageArea,
} from "./policy";
import {
  DEFAULT_STUCK_CONFIG,
  MINUTE,
  evaluateStuck,
  type Snapshot,
  type VerdictKey,
} from "./rules";
import { StuckTracker, changedCharacters } from "./tracker";

const base: Snapshot = {
  trackingStartedAt: 0,
  lastEditAt: null,
  lastRunAt: null,
  resumedAt: null,
  consecutiveFailedSubmissions: 0,
  lastVerdicts: [],
  changedChars: 100,
  failedRuns: 0,
  tabVisible: true,
  systemIdle: false,
};
const snap = (over: Partial<Snapshot>): Snapshot => ({ ...base, ...over });
const verdict = (status: string, testcase: string | null, accepted = false): VerdictKey => ({
  status,
  testcase,
  accepted,
});
const cfg = DEFAULT_STUCK_CONFIG;

describe("defaults", () => {
  it("match the stage plan", () => {
    expect(cfg).toEqual({
      consecutiveFailures: 3,
      inactivityMs: 4 * MINUTE,
      lowProgressChars: 20,
      lowProgressWindowMs: 10 * MINUTE,
      lowProgressMinFailedRuns: 2,
    });
  });
});

describe("rule 1: consecutive failed submissions", () => {
  it.each([
    [0, false],
    [2, false],
    [3, true],
    [7, true],
  ])("%i failures -> stuck=%s", (n, stuck) => {
    const result = evaluateStuck(snap({ consecutiveFailedSubmissions: n, lastEditAt: 1 }), cfg, 1);
    expect(result.stuck).toBe(stuck);
    if (stuck) expect(result.reason).toBe("consecutive_failures");
  });
});

describe("rule 2: same verdict and testcase twice in a row", () => {
  const stuck = (verdicts: VerdictKey[]) =>
    evaluateStuck(snap({ lastVerdicts: verdicts, lastEditAt: 1 }), cfg, 1);

  it("fires for the same failing verdict and testcase", () => {
    expect(stuck([verdict("Wrong Answer", "[1,2]"), verdict("Wrong Answer", "[1,2]")])).toEqual({
      stuck: true,
      reason: "repeated_failure",
    });
  });
  it("ignores different testcases or different verdicts", () => {
    expect(stuck([verdict("Wrong Answer", "[1]"), verdict("Wrong Answer", "[2]")]).stuck).toBe(
      false,
    );
    expect(stuck([verdict("Wrong Answer", "[1]"), verdict("Runtime Error", "[1]")]).stuck).toBe(
      false,
    );
  });
  it("needs two verdicts, a known testcase, and two failures", () => {
    expect(stuck([verdict("Wrong Answer", "[1]")]).stuck).toBe(false);
    expect(
      stuck([verdict("Time Limit Exceeded", null), verdict("Time Limit Exceeded", null)]).stuck,
    ).toBe(false);
    expect(stuck([verdict("Accepted", "[1]", true), verdict("Accepted", "[1]", true)]).stuck).toBe(
      false,
    );
  });
  it("only looks at the last two verdicts", () => {
    const four = [
      verdict("Wrong Answer", "[1]"),
      verdict("Wrong Answer", "[1]"),
      verdict("Wrong Answer", "[9]"),
      verdict("Runtime Error", "[3]"),
    ];
    expect(stuck(four).stuck).toBe(false);
  });
});

describe("rule 3: inactivity", () => {
  const at = (now: number, over: Partial<Snapshot> = {}) =>
    evaluateStuck(snap({ lastEditAt: 0, ...over }), cfg, now);

  it("fires after 4 minutes of no edits and no runs", () => {
    expect(at(4 * MINUTE - 1).stuck).toBe(false);
    expect(at(4 * MINUTE)).toEqual({ stuck: true, reason: "inactivity" });
  });
  it("is reset by an edit or a run", () => {
    expect(at(5 * MINUTE, { lastEditAt: 2 * MINUTE }).stuck).toBe(false);
    expect(at(5 * MINUTE, { lastRunAt: 3 * MINUTE }).stuck).toBe(false);
    expect(at(7 * MINUTE, { lastEditAt: 2 * MINUTE }).stuck).toBe(true);
  });
  it("never fires while the tab is hidden or the system is idle", () => {
    expect(at(10 * MINUTE, { tabVisible: false }).stuck).toBe(false);
    expect(at(10 * MINUTE, { systemIdle: true }).stuck).toBe(false);
  });
  it("restarts the clock when the tab or the system becomes active again", () => {
    expect(at(10 * MINUTE, { resumedAt: 9 * MINUTE }).stuck).toBe(false);
    expect(at(13 * MINUTE + 1, { resumedAt: 9 * MINUTE }).stuck).toBe(true);
  });
  it("measures from the moment tracking started when nothing has happened yet", () => {
    const s = snap({ trackingStartedAt: 100 * MINUTE });
    expect(evaluateStuck(s, cfg, 103 * MINUTE).stuck).toBe(false);
    expect(evaluateStuck(s, cfg, 104 * MINUTE).stuck).toBe(true);
  });
});

describe("rule 4: low progress after failed runs", () => {
  const at = (over: Partial<Snapshot>) =>
    evaluateStuck(
      snap({ lastEditAt: 10 * MINUTE, lastRunAt: 10 * MINUTE, ...over }),
      cfg,
      10 * MINUTE,
    );

  it("fires with < 20 changed chars over 10 minutes after 2 failed runs", () => {
    expect(at({ failedRuns: 2, changedChars: 19 })).toEqual({
      stuck: true,
      reason: "low_progress",
    });
  });
  it("needs at least 2 failed runs, under 20 chars, and a full 10-minute window", () => {
    expect(at({ failedRuns: 1, changedChars: 0 }).stuck).toBe(false);
    expect(at({ failedRuns: 2, changedChars: 20 }).stuck).toBe(false);
    const early = evaluateStuck(
      snap({ failedRuns: 5, changedChars: 0, lastEditAt: 9 * MINUTE, lastRunAt: 9 * MINUTE }),
      cfg,
      9 * MINUTE,
    );
    expect(early.stuck).toBe(false);
  });
});

describe("rule priority and configurability", () => {
  it("reports the first matching rule", () => {
    const s = snap({
      consecutiveFailedSubmissions: 3,
      lastVerdicts: [verdict("Wrong Answer", "x"), verdict("Wrong Answer", "x")],
      failedRuns: 9,
      changedChars: 0,
    });
    expect(evaluateStuck(s, cfg, 20 * MINUTE).reason).toBe("consecutive_failures");
    expect(evaluateStuck({ ...s, consecutiveFailedSubmissions: 0 }, cfg, 20 * MINUTE).reason).toBe(
      "repeated_failure",
    );
  });
  it("uses the config object", () => {
    const strict = { ...cfg, consecutiveFailures: 1 };
    expect(
      evaluateStuck(snap({ consecutiveFailedSubmissions: 1, lastEditAt: 1 }), strict, 1).stuck,
    ).toBe(true);
  });
  it("is not stuck for a student who is working", () => {
    expect(
      evaluateStuck(snap({ lastEditAt: 5 * MINUTE, lastRunAt: 5 * MINUTE }), cfg, 6 * MINUTE).stuck,
    ).toBe(false);
  });
});

describe("StuckTracker with fake time", () => {
  function make() {
    let t = 0;
    const tracker = new StuckTracker(() => t);
    return { tracker, advance: (ms: number) => (t += ms), at: () => t };
  }

  it("treats the first code message as a baseline, not an edit", () => {
    const { tracker, advance } = make();
    tracker.onCode("class Solution: pass");
    advance(MINUTE);
    expect(tracker.snapshot()).toMatchObject({ lastEditAt: null, changedChars: 0 });
    tracker.onCode("class Solution:\n    return 1");
    expect(tracker.snapshot().lastEditAt).toBe(MINUTE);
    expect(tracker.snapshot().changedChars).toBeGreaterThan(0);
  });

  it("keeps a rolling 10-minute window of changed characters", () => {
    const { tracker, advance } = make();
    tracker.onCode("");
    tracker.onCode("x".repeat(30));
    expect(tracker.snapshot().changedChars).toBe(30);
    advance(9 * MINUTE);
    expect(tracker.snapshot().changedChars).toBe(30);
    advance(MINUTE + 1);
    expect(tracker.snapshot().changedChars).toBe(0); // the edit left the window
  });

  it("counts consecutive failed submissions and resets on Accepted", () => {
    const { tracker } = make();
    const wa = { phase: "submit", statusMessage: "Wrong Answer", lastTestcase: "[1]" } as const;
    tracker.onVerdict(wa);
    tracker.onVerdict(wa);
    expect(tracker.snapshot().consecutiveFailedSubmissions).toBe(2);
    tracker.onVerdict({ phase: "run", statusMessage: "Wrong Answer", lastTestcase: "[2]" });
    expect(tracker.snapshot().consecutiveFailedSubmissions).toBe(2); // runs do not count
    tracker.onVerdict({ phase: "submit", statusMessage: "Accepted", lastTestcase: null });
    expect(tracker.snapshot().consecutiveFailedSubmissions).toBe(0);
    expect(tracker.snapshot().failedRuns).toBe(3);
  });

  it("flags 3 consecutive failed submissions as stuck", () => {
    const { tracker } = make();
    for (let i = 0; i < 3; i += 1) {
      tracker.onVerdict({ phase: "submit", statusMessage: "Wrong Answer", lastTestcase: `[${i}]` });
    }
    expect(tracker.evaluate()).toEqual({ stuck: true, reason: "consecutive_failures" });
  });

  it("flags inactivity after 4 minutes but not while hidden, and restarts on return", () => {
    const { tracker, advance } = make();
    tracker.onCode("a");
    advance(3 * MINUTE);
    expect(tracker.evaluate().stuck).toBe(false);
    tracker.setVisible(false);
    advance(30 * MINUTE);
    expect(tracker.evaluate().stuck).toBe(false); // hidden
    tracker.setVisible(true);
    expect(tracker.evaluate().stuck).toBe(false); // the clock restarted on return
    advance(4 * MINUTE);
    expect(tracker.evaluate()).toEqual({ stuck: true, reason: "inactivity" });
  });

  it("does not flag inactivity while the system is idle, and restarts when it is active again", () => {
    const { tracker, advance } = make();
    tracker.setIdle(true);
    advance(20 * MINUTE);
    expect(tracker.evaluate().stuck).toBe(false);
    tracker.setIdle(false);
    advance(3 * MINUTE);
    expect(tracker.evaluate().stuck).toBe(false);
    advance(MINUTE);
    expect(tracker.evaluate().stuck).toBe(true);
  });

  it("flags low progress after failed runs over a full window of tiny edits", () => {
    const { tracker, advance } = make();
    tracker.onCode("a".repeat(100));
    tracker.onVerdict({ phase: "run", statusMessage: "Wrong Answer", lastTestcase: "[1]" });
    advance(2 * MINUTE);
    tracker.onVerdict({ phase: "run", statusMessage: "Wrong Answer", lastTestcase: "[2]" });
    advance(3 * MINUTE);
    tracker.onCode("a".repeat(100) + "b"); // one character
    advance(5 * MINUTE);
    tracker.onVerdict({ phase: "run", statusMessage: "Wrong Answer", lastTestcase: "[3]" }); // activity
    expect(tracker.evaluate()).toEqual({ stuck: true, reason: "low_progress" });
  });

  it("reset() starts over for a new problem but keeps visibility", () => {
    const { tracker, advance } = make();
    tracker.setVisible(false);
    tracker.onCode("a");
    tracker.onVerdict({ phase: "submit", statusMessage: "Wrong Answer", lastTestcase: "x" });
    advance(MINUTE);
    tracker.reset();
    const s = tracker.snapshot();
    expect(s).toMatchObject({
      consecutiveFailedSubmissions: 0,
      failedRuns: 0,
      lastEditAt: null,
      changedChars: 0,
      trackingStartedAt: MINUTE,
      tabVisible: false,
    });
    expect(s.lastVerdicts).toEqual([]);
  });

  it("ignores an unknown verdict status as a failure", () => {
    const { tracker } = make();
    tracker.onVerdict({ phase: "submit", statusMessage: null, lastTestcase: null });
    expect(tracker.snapshot()).toMatchObject({ failedRuns: 0, consecutiveFailedSubmissions: 0 });
  });
});

describe("changedCharacters", () => {
  it.each([
    ["abc", "abc", 0],
    ["abc", "abXc", 1],
    ["", "hello", 5],
    ["hello", "", 5],
    ["abcdef", "abXYef", 2],
    ["a", "b", 1],
  ])("%j -> %j = %i", (a, b, n) => {
    expect(changedCharacters(a, b)).toBe(n);
  });
});

describe("policy", () => {
  const now = 100 * MINUTE;

  it("allows a prompt by default for a problem", () => {
    expect(shouldPrompt(now, EMPTY_POLICY, "two-sum")).toBe(true);
    expect(shouldPrompt(now, EMPTY_POLICY, null)).toBe(false);
  });
  it("enforces a 10-minute cooldown after any nudge", () => {
    const shown = recordNudgeShown(EMPTY_POLICY, now);
    expect(shouldPrompt(now + COOLDOWN_MS - 1, shown, "two-sum")).toBe(false);
    expect(shouldPrompt(now + COOLDOWN_MS, shown, "two-sum")).toBe(true);
    expect(COOLDOWN_MS).toBe(10 * MINUTE);
  });
  it("snoozes for 30 minutes after Not now", () => {
    const snoozed = snooze(EMPTY_POLICY, now);
    expect(shouldPrompt(now + SNOOZE_MS - 1, snoozed, "two-sum")).toBe(false);
    expect(shouldPrompt(now + SNOOZE_MS, snoozed, "two-sum")).toBe(true);
    expect(SNOOZE_MS).toBe(30 * MINUTE);
  });
  it("snooze outlasts the cooldown when both apply", () => {
    const both = snooze(recordNudgeShown(EMPTY_POLICY, now), now);
    expect(shouldPrompt(now + 15 * MINUTE, both, "two-sum")).toBe(false);
    expect(shouldPrompt(now + 31 * MINUTE, both, "two-sum")).toBe(true);
  });
  it("never prompts on a disabled problem, but still on others", () => {
    const off = disableSlug(EMPTY_POLICY, "two-sum");
    expect(shouldPrompt(now + 999 * MINUTE, off, "two-sum")).toBe(false);
    expect(shouldPrompt(now, off, "valid-anagram")).toBe(true);
    expect(disableSlug(off, "two-sum")).toBe(off); // idempotent
  });
  it("round-trips through storage and survives corrupt data", async () => {
    const data: Record<string, unknown> = {};
    const storage: StorageArea = {
      get: async (k) => ({ [k]: data[k] }),
      set: async (items) => void Object.assign(data, items),
    };
    expect(await loadPolicy(storage)).toEqual(EMPTY_POLICY);
    const state = disableSlug(snooze(recordNudgeShown(EMPTY_POLICY, 5), 7), "x");
    await savePolicy(storage, state);
    expect(await loadPolicy(storage)).toEqual(state);
    data.aporiaStuckPolicy = { lastNudgeAt: "oops" };
    expect(await loadPolicy(storage)).toEqual(EMPTY_POLICY);
    const broken: StorageArea = {
      get: async () => {
        throw new Error("storage unavailable");
      },
      set: async () => {
        throw new Error("storage unavailable");
      },
    };
    expect(await loadPolicy(broken)).toEqual(EMPTY_POLICY);
    await expect(savePolicy(broken, state)).resolves.toBeUndefined();
  });
});
