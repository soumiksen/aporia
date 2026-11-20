import { sendMessage } from "../protocol";
import type { EventInput } from "./types";

/**
 * Reports a telemetry event to the service worker, which drops it unless the student has opted
 * in. Never throws and never blocks the UI.
 */
export function track(event: EventInput): void {
  void sendMessage("trackEvent", { ...event, ts: Date.now() }).catch(() => undefined);
}
