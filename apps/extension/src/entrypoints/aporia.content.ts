import { PROBLEM_MATCH_PATTERN, SITE_MATCH_PATTERN } from "../lib/leetcode/constants";
import { fetchProblem, slugFromPath } from "../lib/leetcode/metadata";
import { parseBridgeMessage } from "../lib/messages";
import { pageStore, resetPageState } from "../lib/page-state";
import { MatchPattern } from "wxt/utils/match-patterns";
import { createRoot } from "react-dom/client";
import { createElement } from "react";
import { App } from "../ui/App";
import "../styles/panel.css";

const problemPattern = new MatchPattern(PROBLEM_MATCH_PATTERN);

export default defineContentScript({
  // Matches all of leetcode.com: LeetCode is an SPA, so a script scoped to /problems/* would not be
  // injected when the student navigates from the problem list. We filter by URL in code instead.
  matches: [SITE_MATCH_PATTERN],
  runAt: "document_idle",
  cssInjectionMode: "ui",
  async main(ctx) {
    const sync = (url: URL) => {
      const slug = problemPattern.includes(url.href) ? slugFromPath(url.pathname) : null;
      if (slug === pageStore.getState().slug) return;
      resetPageState(slug);
      if (!slug) return;
      pageStore.setState({ problemStatus: "loading" });
      void fetchProblem(slug).then(({ problem, fromFallback }) => {
        // Ignore stale responses after a quick navigation.
        if (pageStore.getState().slug !== slug) return;
        pageStore.setState({ problem, problemStatus: fromFallback ? "fallback" : "ready" });
      });
    };

    ctx.addEventListener(window, "message", (event) => {
      if (event.source !== window) return;
      const msg = parseBridgeMessage(event.data);
      if (!msg) return;
      if (msg.type === "code") {
        pageStore.setState({ code: msg.code, language: msg.language });
      } else {
        const accepted = msg.statusMessage === "Accepted";
        pageStore.setState({
          failedSinceHint: pageStore.getState().failedSinceHint + (accepted ? 0 : 1),
          lastVerdict: {
            phase: msg.phase,
            status: msg.status,
            statusMessage: msg.statusMessage,
            runtime: msg.runtime,
            lastTestcase: msg.lastTestcase,
            expectedOutput: msg.expectedOutput,
            actualOutput: msg.actualOutput,
          },
        });
      }
    });

    ctx.addEventListener(window, "wxt:locationchange", ({ newUrl }) => sync(newUrl));
    sync(new URL(window.location.href));

    const ui = await createShadowRootUi(ctx, {
      name: "aporia-panel",
      position: "inline",
      anchor: "body",
      isolateEvents: true,
      onMount(container) {
        const root = createRoot(container);
        root.render(createElement(App));
        return root;
      },
      onRemove(root) {
        root?.unmount();
      },
    });
    ui.mount();
  },
});
