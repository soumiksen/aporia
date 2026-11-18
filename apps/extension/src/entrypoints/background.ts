import { API_URL } from "../lib/api-url";
import { getOrCreateDeviceId } from "../lib/device";
import { onMessage, sendMessage } from "../lib/protocol";
import { streamHint } from "../lib/sse";

export default defineBackground(() => {
  const inflight = new Map<string, AbortController>();

  onMessage("getDeviceId", () => getOrCreateDeviceId(browser.storage.local));

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
