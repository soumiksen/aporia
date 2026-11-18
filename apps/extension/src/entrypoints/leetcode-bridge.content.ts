import {
  BRIDGE_SOURCE,
  CHECK_URL_REGEX,
  CODE_DEBOUNCE_MS,
  MONACO_POLL_INTERVAL_MS,
  MONACO_POLL_TIMEOUT_MS,
  PROBLEM_MATCH_PATTERN,
} from "../lib/leetcode/constants";
import {
  modelLanguage,
  parseVerdict,
  pickModel,
  type MonacoLike,
  type MonacoModelLike,
} from "../lib/leetcode/parsers";

// Runs in the page's MAIN world. It must never throw and never alter page behavior.

function post(message: Record<string, unknown>): void {
  try {
    window.postMessage({ source: BRIDGE_SOURCE, ...message }, window.location.origin);
  } catch {
    /* ignore */
  }
}

function getMonaco(): MonacoLike | undefined {
  return (window as unknown as { monaco?: MonacoLike }).monaco;
}

function observeVerdict(url: string, text: string): void {
  try {
    if (!CHECK_URL_REGEX.test(url)) return;
    const verdict = parseVerdict(url, JSON.parse(text));
    if (verdict) post({ type: "verdict", ...verdict });
  } catch {
    /* ignore malformed bodies */
  }
}

function patchFetch(): void {
  const original = window.fetch;
  window.fetch = function patchedFetch(this: unknown, ...args: Parameters<typeof fetch>) {
    const promise = original.apply(this, args);
    try {
      const input = args[0];
      const url =
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (CHECK_URL_REGEX.test(url)) {
        promise
          .then((res) => res.clone().text())
          .then((text) => observeVerdict(url, text))
          .catch(() => undefined);
      }
    } catch {
      /* ignore */
    }
    return promise;
  };
}

function patchXhr(): void {
  const proto = XMLHttpRequest.prototype;
  const originalOpen = proto.open;
  proto.open = function patchedOpen(this: XMLHttpRequest, ...args: unknown[]) {
    try {
      const url = String(args[1]);
      if (CHECK_URL_REGEX.test(url)) {
        this.addEventListener("load", () => {
          try {
            if (this.responseType === "" || this.responseType === "text") {
              observeVerdict(url, this.responseText);
            }
          } catch {
            /* ignore */
          }
        });
      }
    } catch {
      /* ignore */
    }
    return (originalOpen as (...a: unknown[]) => void).apply(this, args);
  } as typeof proto.open;
}

function watchEditor(): void {
  let bound: MonacoModelLike | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let subscription: { dispose(): void } | undefined;

  const send = (model: MonacoModelLike) => {
    post({ type: "code", code: model.getValue(), language: modelLanguage(model) });
  };

  const bind = (model: MonacoModelLike) => {
    subscription?.dispose();
    bound = model;
    send(model);
    subscription = model.onDidChangeContent?.(() => {
      clearTimeout(timer);
      timer = setTimeout(() => send(model), CODE_DEBOUNCE_MS);
    });
  };

  const started = Date.now();
  const poll = setInterval(() => {
    try {
      const model = pickModel(getMonaco());
      if (model && model !== bound) bind(model);
      // Initial attach budget; once attached keep polling slowly to follow model swaps (SPA).
      if (!bound && Date.now() - started > MONACO_POLL_TIMEOUT_MS) clearInterval(poll);
    } catch {
      /* ignore */
    }
  }, MONACO_POLL_INTERVAL_MS);
}

export default defineContentScript({
  matches: [PROBLEM_MATCH_PATTERN],
  world: "MAIN",
  runAt: "document_idle",
  main() {
    patchFetch();
    patchXhr();
    watchEditor();
  },
});
