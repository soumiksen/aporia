import { create } from "zustand";

export type HintStatus = "idle" | "streaming" | "done" | "error";

export interface HintState {
  status: HintStatus;
  text: string;
  level: number;
  errorCode: string | null;
  errorMessage: string | null;
  start: (level: number) => void;
  append: (text: string) => void;
  finish: () => void;
  fail: (code: string, message: string) => void;
  reset: () => void;
}

export const useHintStore = create<HintState>((set) => ({
  status: "idle",
  text: "",
  level: 1,
  errorCode: null,
  errorMessage: null,
  start: (level) =>
    set({ status: "streaming", text: "", level, errorCode: null, errorMessage: null }),
  append: (text) => set((s) => ({ text: s.text + text })),
  finish: () => set({ status: "done" }),
  fail: (code, message) => set({ status: "error", errorCode: code, errorMessage: message }),
  reset: () => set({ status: "idle", text: "", errorCode: null, errorMessage: null }),
}));
