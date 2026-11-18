import { defineExtensionMessaging } from "@webext-core/messaging";
import type { HintEvent, HintRequest } from "./messages";

/** The single typed protocol map for all extension-internal messaging. */
interface ProtocolMap {
  /** Content script -> service worker. Starts a stream; events return via `hintEvent`. */
  getHint(data: { requestId: string; request: HintRequest }): void;
  /** Content script -> service worker. Aborts an in-flight stream. */
  cancelHint(data: { requestId: string }): void;
  /** Any context -> service worker. Returns (creating if needed) the device UUID. */
  getDeviceId(): string;
  /** Service worker -> content script (tab). One streamed event. */
  hintEvent(data: { requestId: string; event: HintEvent }): void;
}

export const { sendMessage, onMessage } = defineExtensionMessaging<ProtocolMap>();
