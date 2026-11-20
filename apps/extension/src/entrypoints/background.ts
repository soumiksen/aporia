import { API_URL } from "../lib/api-url";
import { getConsent, setConsent } from "../lib/consent";
import { getOrCreateDeviceId } from "../lib/device";
import { postEvents } from "../lib/events/post";
import { EventQueue } from "../lib/events/queue";
import { onMessage, sendMessage } from "../lib/protocol";
import { postRating } from "../lib/rating";
import { streamHint } from "../lib/sse";

export default defineBackground(() => {
  const inflight = new Map<string, AbortController>();

  // Telemetry: queued only after explicit opt-in, batched, retried with backoff.
  const queue = new EventQueue({
    isEnabled: async () => (await getConsent(browser.storage.local)).enabled,
    send: async (events) =>
      postEvents({
        apiUrl: API_URL,
        deviceId: await getOrCreateDeviceId(browser.storage.local),
        events,
      }),
    storage: browser.storage.local,
  });
  void queue.load(); // survive service-worker restarts (and flush what was waiting)
  onMessage("trackEvent", async ({ data }) => void (await queue.enqueue(data)));
  onMessage("getConsent", () => getConsent(browser.storage.local));
  onMessage("setConsent", async ({ data }) => {
    const consent = await setConsent(browser.storage.local, data.enabled);
    if (!consent.enabled) await queue.clear(); // opting out drops anything still waiting
    return consent;
  });

  onMessage("getDeviceId", () => getOrCreateDeviceId(browser.storage.local));

  onMessage("rateHint", async ({ data }) =>
    postRating({
      apiUrl: API_URL,
      deviceId: await getOrCreateDeviceId(browser.storage.local),
      hintId: data.hintId,
      rating: data.rating,
    }),
  );

  // System idle: 60 s detection interval; state changes are relayed to open LeetCode tabs.
  const IDLE_INTERVAL_S = 60;
  browser.idle.setDetectionInterval(IDLE_INTERVAL_S);
  browser.idle.onStateChanged.addListener(async (state) => {
    const tabs = await browser.tabs.query({ url: "https://leetcode.com/*" });
    for (const tab of tabs) {
      if (tab.id !== undefined) {
        sendMessage("idleState", { idle: state !== "active" }, tab.id).catch(() => undefined);
      }
    }
  });
  onMessage(
    "getIdleState",
    async () => (await browser.idle.queryState(IDLE_INTERVAL_S)) !== "active",
  );

  onMessage("cancelHint", ({ data }) => {
    inflight.get(data.requestId)?.abort();
    inflight.delete(data.requestId);
  });

  onMessage("getHint", ({ data, sender }) => {
    const tabId = sender.tab?.id;
    if (tabId === undefined) return;
    const { requestId, request } = data;
    inflight.get(requestId)?.abort();
    const controller = new AbortController();
    inflight.set(requestId, controller);

    // Fire and forget: events are relayed to the originating tab as they arrive.
    void (async () => {
      const deviceId = await getOrCreateDeviceId(browser.storage.local);
      await streamHint({
        apiUrl: API_URL,
        deviceId,
        request,
        signal: controller.signal,
        onEvent(event) {
          sendMessage("hintEvent", { requestId, event }, tabId).catch(() => controller.abort());
        },
      });
      inflight.delete(requestId);
    })();
  });
});
