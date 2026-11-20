import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { pageStore, resetPageState } from "@/lib/page-state";
import { MINUTE } from "@/lib/stuck/rules";
import { COOLDOWN_MS, SNOOZE_MS, loadPolicy, type StorageArea } from "@/lib/stuck/policy";
import {
  AUTO_DISMISS_MS,
  EVALUATE_EVERY_MS,
  resetLabelSession,
  useStuckNudge,
  type UseStuckNudgeOptions,
} from "./useStuckNudge";

const h = vi.hoisted(() => ({
  tracked: [] as Record<string, unknown>[],
  idleListener: null as null | ((m: { data: { idle: boolean } }) => void),
}));

vi.mock("@/lib/events/track", () => ({
  track: (event: Record<string, unknown>) => void h.tracked.push(event),
}));
vi.mock("@/lib/protocol", () => ({
  sendMessage: vi.fn(async () => false),
  onMessage: (_type: string, cb: (m: { data: { idle: boolean } }) => void) => {
    h.idleListener = cb;
    return () => {
      h.idleListener = null;
    };
  },
}));

function memoryStorage() {
  const data: Record<string, unknown> = {};
  const storage: StorageArea = {
    get: async (key) => ({ [key]: data[key] }),
    set: async (items) => void Object.assign(data, items),
  };
  return { storage, data };
}

function failedSubmit(testcase: string) {
  return {
    phase: "submit" as const,
    status: "11",
    statusMessage: "Wrong Answer",
    runtime: null,
    lastTestcase: testcase,
    expectedOutput: null,
    actualOutput: null,
  };
}

/** Three failed submissions in a row: the "consecutive failures" rule. */
function failThreeTimes() {
  for (let i = 0; i < 3; i += 1) {
    act(() => pageStore.setState({ lastVerdict: failedSubmit(`case-${i}`) }));
  }
}

/** Advances time in evaluation-sized steps; returns the elapsed ms when the bubble first shows. */
async function advanceUntilBubble(
  result: { current: { bubbleVisible: boolean } },
  maxMs: number,
  step = EVALUATE_EVERY_MS,
): Promise<number | null> {
  for (let elapsed = step; elapsed <= maxMs; elapsed += step) {
    await act(async () => vi.advanceTimersByTimeAsync(step));
    if (result.current.bubbleVisible) return elapsed;
  }
  return null;
}

async function setup(over: Partial<UseStuckNudgeOptions> = {}, store = memoryStorage()) {
  const onAccept = vi.fn();
  const rendered = renderHook(
    (props: Partial<UseStuckNudgeOptions>) =>
      useStuckNudge({
        slug: "two-sum",
        panelOpen: false,
        onAccept,
        storage: store.storage,
        random: () => 0.99, // never ask the label question unless a test says so
        ...props,
      }),
    { initialProps: over },
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0); // let the policy load
  });
  return { ...rendered, onAccept, store };
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(1_000_000);
  h.tracked.length = 0;
  resetPageState("two-sum");
  resetLabelSession();
});
afterEach(() => vi.useRealTimers());

describe("useStuckNudge", () => {
  it("does nothing while the student is working normally", async () => {
    const { result } = await setup();
    act(() => pageStore.setState({ code: "a" }));
    act(() => pageStore.setState({ code: "ab" }));
    await act(async () => vi.advanceTimersByTimeAsync(2 * MINUTE));
    expect(result.current.bubbleVisible).toBe(false);
    expect(h.tracked).toEqual([]);
  });

  it("offers a nudge after 3 failed submissions, and never opens a hint by itself", async () => {
    const { result, onAccept } = await setup();
    failThreeTimes();
    expect(result.current.bubbleVisible).toBe(true);
    expect(onAccept).not.toHaveBeenCalled();
    expect(h.tracked).toMatchObject([
      { type: "stuck_prompt_shown", slug: "two-sum", reason: "consecutive_failures" },
    ]);
  });

  it("'Yes' hands over to the caller (which asks a level-1 hint) and hides the bubble", async () => {
    const { result, onAccept } = await setup();
    failThreeTimes();
    act(() => result.current.yes());
    expect(onAccept).toHaveBeenCalledTimes(1);
    expect(result.current.bubbleVisible).toBe(false);
    expect(h.tracked.at(-1)).toMatchObject({ type: "stuck_prompt_accepted", slug: "two-sum" });
  });

  it("never appears during the 10-minute cooldown, even though the student is still stuck", async () => {
    const { result } = await setup();
    failThreeTimes();
    expect(result.current.bubbleVisible).toBe(true);
    act(() => result.current.yes()); // answered Yes: the cooldown still applies
    act(() => pageStore.setState({ lastVerdict: failedSubmit("again") })); // still stuck
    expect(result.current.bubbleVisible).toBe(false);
    const appearedAfter = await advanceUntilBubble(result, 20 * MINUTE);
    expect(appearedAfter).not.toBeNull();
    expect(appearedAfter as number).toBeGreaterThanOrEqual(COOLDOWN_MS); // never earlier
    expect(appearedAfter as number).toBeLessThan(COOLDOWN_MS + 2 * EVALUATE_EVERY_MS);
  });

  it("auto-dismisses after 12 seconds and counts that as 'not now' (30-minute snooze)", async () => {
    const { result, store } = await setup();
    failThreeTimes();
    await act(async () => vi.advanceTimersByTimeAsync(AUTO_DISMISS_MS - 1));
    expect(result.current.bubbleVisible).toBe(true);
    await act(async () => vi.advanceTimersByTimeAsync(1));
    expect(result.current.bubbleVisible).toBe(false);
    expect(h.tracked.at(-1)).toMatchObject({
      type: "stuck_prompt_dismissed",
      reason: "consecutive_failures",
    });
    const policy = await loadPolicy(store.storage);
    expect(policy.snoozedUntil).toBe(Date.now() + SNOOZE_MS);
    // snoozed: nothing for 30 minutes
    await act(async () => vi.advanceTimersByTimeAsync(SNOOZE_MS - 2 * EVALUATE_EVERY_MS));
    expect(result.current.bubbleVisible).toBe(false);
  });

  it("'Not now' snoozes for 30 minutes and persists across reloads", async () => {
    const first = await setup();
    failThreeTimes();
    act(() => first.result.current.notNow());
    expect(first.result.current.bubbleVisible).toBe(false);
    first.unmount();
    // a new page load with the same storage
    resetPageState("two-sum");
    const second = await setup({}, first.store);
    failThreeTimes();
    expect(second.result.current.bubbleVisible).toBe(false);
  });

  it("'Never on this problem' is persistent for that slug only", async () => {
    const first = await setup();
    failThreeTimes();
    act(() => first.result.current.never());
    first.unmount();
    vi.setSystemTime(Date.now() + 24 * 60 * MINUTE);
    resetPageState("two-sum");
    const again = await setup({}, first.store);
    failThreeTimes();
    expect(again.result.current.bubbleVisible).toBe(false); // a day later, still disabled
    again.unmount();
    resetPageState("valid-anagram");
    const other = await setup({ slug: "valid-anagram" }, first.store);
    failThreeTimes();
    expect(other.result.current.bubbleVisible).toBe(true);
  });

  it("does not interrupt while the panel is open and hides a pending bubble when it opens", async () => {
    const { result, rerender } = await setup({ panelOpen: true });
    failThreeTimes();
    expect(result.current.bubbleVisible).toBe(false);
    rerender({ panelOpen: false });
    act(() => pageStore.setState({ lastVerdict: failedSubmit("x") }));
    expect(result.current.bubbleVisible).toBe(true);
    rerender({ panelOpen: true });
    expect(result.current.bubbleVisible).toBe(false);
  });

  it("detects inactivity with the periodic evaluation, but not while the tab is hidden", async () => {
    const { result } = await setup();
    act(() => pageStore.setState({ code: "a" }));
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    act(() => void document.dispatchEvent(new Event("visibilitychange")));
    expect(await advanceUntilBubble(result, 10 * MINUTE)).toBeNull(); // hidden: never
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    act(() => void document.dispatchEvent(new Event("visibilitychange")));
    const after = await advanceUntilBubble(result, 6 * MINUTE);
    expect(after).not.toBeNull(); // the 4-minute clock restarted when the tab came back
    expect(after as number).toBeGreaterThanOrEqual(4 * MINUTE);
    expect(after as number).toBeLessThan(4 * MINUTE + 2 * EVALUATE_EVERY_MS);
    expect(h.tracked.at(-1)).toMatchObject({ reason: "inactivity" });
  });

  it("does not fire inactivity while the system is idle", async () => {
    const { result } = await setup();
    act(() => h.idleListener?.({ data: { idle: true } }));
    await act(async () => vi.advanceTimersByTimeAsync(10 * MINUTE));
    expect(result.current.bubbleVisible).toBe(false);
  });

  it("resets the tracker when the problem changes", async () => {
    const { result } = await setup();
    act(() => pageStore.setState({ lastVerdict: failedSubmit("a") }));
    act(() => pageStore.setState({ lastVerdict: failedSubmit("b") }));
    act(() => resetPageState("valid-anagram"));
    act(() => pageStore.setState({ lastVerdict: failedSubmit("c") }));
    expect(result.current.bubbleVisible).toBe(false); // only one failure on the new problem
  });

  describe("'Were you actually stuck?'", () => {
    it("is asked after a dismissal with 30% probability, at most once per session", async () => {
      const { result } = await setup({ random: () => 0.1 }); // below 0.3: ask
      failThreeTimes();
      act(() => result.current.notNow());
      expect(result.current.labelVisible).toBe(true);
      act(() => result.current.answerLabel(true));
      expect(result.current.labelVisible).toBe(false);
      expect(h.tracked.at(-1)).toMatchObject({ type: "stuck_label", was_stuck: true });
      // later in the same session: never asked again
      vi.setSystemTime(Date.now() + 2 * 60 * MINUTE);
      act(() => pageStore.setState({ lastVerdict: failedSubmit("later") }));
      expect(result.current.bubbleVisible).toBe(true);
      act(() => result.current.notNow());
      expect(result.current.labelVisible).toBe(false);
    });

    it("is skipped when the dice say no", async () => {
      const { result } = await setup({ random: () => 0.5 });
      failThreeTimes();
      act(() => result.current.notNow());
      expect(result.current.labelVisible).toBe(false);
    });
  });
});
