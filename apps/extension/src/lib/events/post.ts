import type { AporiaEvent } from "./types";

export interface PostEventsOptions {
  apiUrl: string;
  deviceId: string;
  events: AporiaEvent[];
  fetchFn?: typeof fetch;
}

/** Sends a batch (max 50). Returns whether the server accepted it; never throws. */
export async function postEvents(opts: PostEventsOptions): Promise<boolean> {
  const fetchFn = opts.fetchFn ?? fetch;
  try {
    const res = await fetchFn(`${opts.apiUrl}/v1/events`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-aporia-device": opts.deviceId },
      body: JSON.stringify({ events: opts.events }),
    });
    // A 4xx means the batch itself is invalid: retrying cannot help, so treat it as handled.
    return res.ok || (res.status >= 400 && res.status < 500 && res.status !== 429);
  } catch {
    return false;
  }
}
