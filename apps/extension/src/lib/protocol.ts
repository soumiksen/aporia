import { defineExtensionMessaging } from "@webext-core/messaging";
import type { AporiaEvent } from "./events/types";
import type { HintEvent, HintRequest } from "./messages";

/** The single typed protocol map for all extension-internal messaging. */
interface ProtocolMap {
  /** Content script -> service worker. Starts a stream; events return via `hintEvent`. */
  getHint(data: { requestId: string; request: HintRequest }): void;
  /** Content script -> service worker. Aborts an in-flight stream. */
  cancelHint(data: { requestId: string }): void;
  /** Content script -> service worker. Queues a telemetry event (dropped unless opted in). */
  trackEvent(data: AporiaEvent): void;
  /** Service worker -> content script (tab). The system idle state changed. */
  idleState(data: { idle: boolean }): void;
  /** Content script -> service worker. Whether the system is currently idle (60 s interval). */
  getIdleState(): boolean;
  /** Content script -> service worker. Rates a delivered hint (1 = not helpful, 5 = great). */
  rateHint(data: { hintId: string; rating: number }): boolean;
  /** Any context -> service worker. Returns (creating if needed) the device UUID. */
  getDeviceId(): string;
  /** Service worker -> content script (tab). One streamed event. */
  hintEvent(data: { requestId: string; event: HintEvent }): void;
}

export const { sendMessage, onMessage } = defineExtensionMessaging<ProtocolMap>();
