import { createStore } from "zustand/vanilla";
import type { VerdictMessage } from "./messages";
import type { ProblemInfo } from "./leetcode/metadata";

export interface PageState {
  slug: string | null;
  problem: ProblemInfo | null;
  problemStatus: "idle" | "loading" | "ready" | "fallback";
  code: string | null;
  language: string | null;
  lastVerdict: Omit<VerdictMessage, "source" | "type"> | null;
  /** Failed run/submit verdicts observed since the last hint was requested. */
  failedSinceHint: number;
}

const initial: PageState = {
  slug: null,
  problem: null,
  problemStatus: "idle",
  code: null,
  language: null,
  lastVerdict: null,
  failedSinceHint: 0,
};

/** Latest observed LeetCode page state, shared by the content script and the UI. */
export const pageStore = createStore<PageState>(() => ({ ...initial }));

export function resetPageState(slug: string | null): void {
  pageStore.setState({ ...initial, slug });
}
