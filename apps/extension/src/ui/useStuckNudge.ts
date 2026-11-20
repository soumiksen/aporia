import { useCallback, useEffect, useRef, useState } from "react";
import { track } from "@/lib/events/track";
import { pageStore } from "@/lib/page-state";
import { onMessage, sendMessage } from "@/lib/protocol";
import {
  EMPTY_POLICY,
  disableSlug,
  loadPolicy,
  recordNudgeShown,
  savePolicy,
  shouldPrompt,
  snooze,
  type PolicyState,
  type StorageArea,
} from "@/lib/stuck/policy";
import type { StuckReason } from "@/lib/stuck/rules";
import { StuckTracker } from "@/lib/stuck/tracker";

export const EVALUATE_EVERY_MS = 15_000;
export const AUTO_DISMISS_MS = 12_000;
export const LABEL_PROBABILITY = 0.3;

// "At most once per session": a session is the lifetime of the content script (a page load).
let labelAskedThisSession = false;
export function resetLabelSession(): void {
  labelAskedThisSession = false;
}

function memoryStorage(): StorageArea {
  const data: Record<string, unknown> = {};
  return {
    get: async (key) => ({ [key]: data[key] }),
    set: async (items) => void Object.assign(data, items),
  };
}

function defaultStorage(): StorageArea {
  try {
    return browser.storage.local as unknown as StorageArea;
  } catch {
    return memoryStorage(); // outside the extension (unit tests)
  }
}

export interface UseStuckNudgeOptions {
  slug: string | null;
  panelOpen: boolean;
  /** Called when the student answers "Yes": the caller opens the panel and asks a level-1 hint. */
  onAccept: () => void;
  random?: () => number;
  storage?: StorageArea;
  evaluateEveryMs?: number;
  autoDismissMs?: number;
}

export function useStuckNudge(options: UseStuckNudgeOptions) {
  const {
    slug,
    panelOpen,
    onAccept,
    random = Math.random,
    evaluateEveryMs = EVALUATE_EVERY_MS,
    autoDismissMs = AUTO_DISMISS_MS,
  } = options;
  const [bubbleVisible, setBubbleVisible] = useState(false);
  const [labelVisible, setLabelVisible] = useState(false);

  const tracker = useRef(new StuckTracker());
  const policy = useRef<PolicyState>(EMPTY_POLICY);
  const policyLoaded = useRef(false);
  const storage = useRef<StorageArea | null>(null);
  const reason = useRef<StuckReason | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const live = useRef({ slug, panelOpen, bubbleVisible, labelVisible, onAccept, random });
  live.current = { slug, panelOpen, bubbleVisible, labelVisible, onAccept, random };

  const clearTimer = () => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
  };

  const persist = (next: PolicyState) => {
    policy.current = next;
    if (storage.current) void savePolicy(storage.current, next);
  };

  const dismiss = useCallback((kind: "not_now" | "never") => {
    clearTimer();
    const { slug: current } = live.current;
    persist(
      kind === "never" && current
        ? disableSlug(policy.current, current)
        : snooze(policy.current, Date.now()),
    );
    setBubbleVisible(false);
    track({
      type: "stuck_prompt_dismissed",
      slug: current ?? undefined,
      reason: reason.current ?? undefined,
    });
    if (!labelAskedThisSession && live.current.random() < LABEL_PROBABILITY) {
      labelAskedThisSession = true;
      setLabelVisible(true);
    }
  }, []);

  const evaluate = useCallback(() => {
    const now = Date.now();
    const cur = live.current;
    if (!policyLoaded.current || cur.bubbleVisible || cur.labelVisible || cur.panelOpen) return;
    const result = tracker.current.evaluate();
    if (!result.stuck || !shouldPrompt(now, policy.current, cur.slug)) return;
    reason.current = result.reason;
    persist(recordNudgeShown(policy.current, now)); // the cooldown starts when it is shown
    setBubbleVisible(true);
    track({
      type: "stuck_prompt_shown",
      slug: cur.slug ?? undefined,
      reason: result.reason ?? undefined,
    });
    clearTimer();
    timer.current = setTimeout(() => dismiss("not_now"), autoDismissMs); // auto-dismiss = not now
  }, [autoDismissMs, dismiss]);

  // Load the persisted policy once.
  useEffect(() => {
    storage.current = options.storage ?? defaultStorage();
    let cancelled = false;
    void loadPolicy(storage.current).then((loaded) => {
      if (cancelled) return;
      policy.current = loaded;
      policyLoaded.current = true;
      evaluate();
    });
    return () => {
      cancelled = true;
      clearTimer();
    };
  }, []);

  // Feed bridge signals into the tracker.
  useEffect(() => {
    const t = tracker.current;
    const initial = pageStore.getState();
    if (initial.code !== null) t.onCode(initial.code);
    const unsubscribe = pageStore.subscribe((state, prev) => {
      if (state.slug !== prev.slug) {
        t.reset();
        setBubbleVisible(false);
        clearTimer();
      }
      if (state.code !== null && state.code !== prev.code) t.onCode(state.code);
      if (state.lastVerdict && state.lastVerdict !== prev.lastVerdict) {
        t.onVerdict({
          phase: state.lastVerdict.phase,
          statusMessage: state.lastVerdict.statusMessage,
          lastTestcase: state.lastVerdict.lastTestcase,
        });
      }
      evaluate();
    });
    return unsubscribe;
  }, [evaluate]);

  // Page visibility and system idle.
  useEffect(() => {
    const t = tracker.current;
    const onVisibility = () => {
      t.setVisible(document.visibilityState === "visible");
      evaluate();
    };
    t.setVisible(document.visibilityState === "visible");
    document.addEventListener("visibilitychange", onVisibility);
    const removeIdle = onMessage("idleState", ({ data }) => {
      t.setIdle(data.idle);
      evaluate();
    });
    void sendMessage("getIdleState")
      .then((idle) => t.setIdle(idle))
      .catch(() => undefined);
    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      removeIdle();
    };
  }, [evaluate]);

  // Periodic evaluation (inactivity has no event to wake us up).
  useEffect(() => {
    const id = setInterval(evaluate, evaluateEveryMs);
    return () => clearInterval(id);
  }, [evaluate, evaluateEveryMs]);

  // Opening the panel by hand makes the bubble moot.
  useEffect(() => {
    if (panelOpen && bubbleVisible) {
      clearTimer();
      setBubbleVisible(false);
    }
  }, [panelOpen, bubbleVisible]);

  const yes = useCallback(() => {
    clearTimer();
    setBubbleVisible(false);
    track({
      type: "stuck_prompt_accepted",
      slug: live.current.slug ?? undefined,
      reason: reason.current ?? undefined,
    });
    live.current.onAccept();
  }, []);

  const answerLabel = useCallback((wasStuck: boolean) => {
    setLabelVisible(false);
    track({ type: "stuck_label", slug: live.current.slug ?? undefined, was_stuck: wasStuck });
  }, []);

  return {
    bubbleVisible,
    labelVisible,
    yes,
    notNow: () => dismiss("not_now"),
    never: () => dismiss("never"),
    answerLabel,
  };
}
