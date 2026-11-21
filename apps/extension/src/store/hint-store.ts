import { create } from "zustand";
import type { Source } from "../lib/messages";

export type HintStatus = "idle" | "streaming" | "done" | "error";

export const MAX_LEVEL = 4;
export const MAX_MESSAGE_CHARS = 300;

export interface HintState {
  status: HintStatus;
  text: string;
  /** The level being requested while streaming, then the level the server actually served. */
  level: number;
  hintId: string | null;
  /** false when the API cannot run code for this problem (prompt-only hints). */
  supported: boolean;
  /** Study notes the served hint was based on. */
  sources: Source[];
  rated: boolean;
  errorCode: string | null;
  errorMessage: string | null;
  start: (level: number) => void;
  append: (text: string) => void;
  finish: (info?: {
    hintId?: string;
    level?: number;
    supported?: boolean;
    sources?: Source[];
  }) => void;
  fail: (code: string, message: string) => void;
  markRated: () => void;
  reset: () => void;
}

export const useHintStore = create<HintState>((set) => ({
  status: "idle",
  text: "",
  level: 1,
  hintId: null,
  supported: true,
  sources: [],
  rated: false,
  errorCode: null,
  errorMessage: null,
  start: (level) =>
    set({
      status: "streaming",
      text: "",
      level,
      hintId: null,
      sources: [],
      rated: false,
      errorCode: null,
      errorMessage: null,
    }),
  append: (text) => set((s) => ({ text: s.text + text })),
  finish: (info) =>
    set((s) => ({
      status: "done",
      hintId: info?.hintId ?? s.hintId,
      level: info?.level ?? s.level,
      supported: info?.supported ?? s.supported,
      sources: info?.sources ?? s.sources,
    })),
  fail: (code, message) => set({ status: "error", errorCode: code, errorMessage: message }),
  markRated: () => set({ rated: true }),
  reset: () =>
    set({
      status: "idle",
      text: "",
      level: 1,
      hintId: null,
      supported: true,
      sources: [],
      rated: false,
      errorCode: null,
      errorMessage: null,
    }),
}));
