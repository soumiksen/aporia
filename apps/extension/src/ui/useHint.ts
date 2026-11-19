import { useCallback, useEffect, useRef } from "react";
import { useStore } from "zustand";
import { problemFromPage } from "@/lib/leetcode/metadata";
import type { HintRequest } from "@/lib/messages";
import { pageStore } from "@/lib/page-state";
import { onMessage, sendMessage } from "@/lib/protocol";
import { MAX_LEVEL, MAX_MESSAGE_CHARS, useHintStore } from "@/store/hint-store";

export interface AskOptions {
  level: number;
  studentMessage?: string;
}

/** Builds the request from the latest bridge state. Never blocks on missing code or metadata. */
export function buildRequest(options: AskOptions): HintRequest | null {
  const s = pageStore.getState();
  if (!s.slug) return null;
  const message = options.studentMessage?.trim().slice(0, MAX_MESSAGE_CHARS);
  return {
    problem: s.problem ?? problemFromPage(s.slug, document),
    code: s.code ?? "",
    language: s.language ?? "unknown",
    level: Math.max(1, Math.min(MAX_LEVEL, options.level)),
    student_message: message ? message : null,
    failed_attempts: s.failedSinceHint,
    last_verdict: s.lastVerdict?.statusMessage ?? null,
  };
}

export function useHint() {
  const requestId = useRef<string | null>(null);
  const slug = useStore(pageStore, (s) => s.slug);
  const codeKnown = useStore(pageStore, (s) => s.code !== null);

  const cancel = useCallback(() => {
    const id = requestId.current;
    requestId.current = null;
    if (id) void sendMessage("cancelHint", { requestId: id }).catch(() => undefined);
    useHintStore.getState().reset();
  }, []);

  // Relay service-worker events into the store; ignore events from stale requests.
  useEffect(() => {
    return onMessage("hintEvent", ({ data }) => {
      if (data.requestId !== requestId.current) return;
      const store = useHintStore.getState();
      const { event } = data;
      if (event.event === "token") store.append(event.text);
      else if (event.event === "done")
        store.finish({ hintId: event.hint_id, level: event.level, supported: event.supported });
      else store.fail(event.code, event.message);
    });
  }, []);

  // A different problem invalidates any in-flight or finished hint.
  useEffect(() => {
    cancel();
  }, [slug, cancel]);

  const ask = useCallback((options: AskOptions = { level: 1 }) => {
    const request = buildRequest(options);
    if (!request) return;
    const id = crypto.randomUUID();
    requestId.current = id;
    pageStore.setState({ failedSinceHint: 0 }); // the counter is "failures since the last hint"
    useHintStore.getState().start(request.level ?? 1);
    sendMessage("getHint", { requestId: id, request }).catch(() => {
      if (requestId.current !== id) return;
      useHintStore
        .getState()
        .fail("extension", "Aporia lost contact with its background worker. Reload the page.");
    });
  }, []);

  const rate = useCallback((rating: number) => {
    const { hintId, rated } = useHintStore.getState();
    if (!hintId || rated) return;
    useHintStore.getState().markRated();
    void sendMessage("rateHint", { hintId, rating }).catch(() => undefined);
  }, []);

  return { ask, cancel, rate, slug, codeKnown };
}
