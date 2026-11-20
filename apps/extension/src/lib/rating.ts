export interface RatingOptions {
  apiUrl: string;
  deviceId: string;
  hintId: string;
  rating: number;
  fetchFn?: typeof fetch;
}

/** Sends a hint rating. Returns whether the server accepted it; never throws. */
export async function postRating(opts: RatingOptions): Promise<boolean> {
  const fetchFn = opts.fetchFn ?? fetch;
  try {
    const res = await fetchFn(`${opts.apiUrl}/v1/hints/${encodeURIComponent(opts.hintId)}/rating`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-aporia-device": opts.deviceId },
      body: JSON.stringify({ rating: opts.rating }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
