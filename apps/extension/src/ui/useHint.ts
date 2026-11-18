import { useCallback, useEffect, useRef } from "react";
import { useStore } from "zustand";
import { problemFromPage } from "@/lib/leetcode/metadata";
import type { HintRequest } from "@/lib/messages";
import { pageStore } from "@/lib/page-state";
import { onMessage, sendMessage } from "@/lib/protocol";
import { useHintStore } from "@/store/hint-store";

/** Builds the request from the latest bridge state. Never blocks on missing code or metadata. */
export function buildRequest(): HintRequest | null {
  const s = pageStore.getState();
  if (!s.slug) return null;
  return {
    problem: s.problem ?? problemFromPage(s.slug, document),
    code: s.code ?? "",
    language: s.language ?? "unknown",
    level: 1,
    student_message: null,
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
      else if (event.event === "done") store.finish();
      else store.fail(event.code, event.message);
    });
  }, []);

  // A different problem invalidates any in-flight or finished hint.
  useEffect(() => {
    cancel();
  }, [slug, cancel]);

  const ask = useCallback(() => {
    const request = buildRequest();
    if (!request) return;
    const id = crypto.randomUUID();
    requestId.current = id;
    useHintStore.getState().start(1);
    sendMessage("getHint", { requestId: id, request }).catch(() => {
      if (requestId.current !== id) return;
      useHintStore
        .getState()
        .fail("extension", "Aporia lost contact with its background worker. Reload the page.");
    });
  }, []);

  return { ask, cancel, slug, codeKnown };
}
