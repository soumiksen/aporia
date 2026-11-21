export interface AttemptOptions {
  apiUrl: string;
  deviceId: string;
  slug: string;
  verdict: string;
  fetchFn?: typeof fetch;
}

/**
 * The verdict to report for a page verdict, or null. Only Accepted *submissions* are reported
 * (runs are not attempts). Never includes code.
 */
export function verdictToReport(msg: {
  phase: string;
  statusMessage: string | null;
}): string | null {
  return msg.phase === "submit" && msg.statusMessage === "Accepted" ? "Accepted" : null;
}

/** Tells the server about a submission outcome (slug and verdict only). Never throws. */
export async function postAttempt(opts: AttemptOptions): Promise<boolean> {
  const fetchFn = opts.fetchFn ?? fetch;
  try {
    const res = await fetchFn(`${opts.apiUrl}/v1/attempts`, {
      method: "POST",
      headers: { "content-type": "application/json", "x-aporia-device": opts.deviceId },
      body: JSON.stringify({ slug: opts.slug, verdict: opts.verdict }),
    });
    return res.ok;
  } catch {
    return false;
  }
}
