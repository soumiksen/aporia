// Error tracking for the extension, enabled only when VITE_SENTRY_DSN is set at build time.
// Student code and problem text must never leave the browser through an error report.

export const FILTERED = "[Filtered]";
const SENSITIVE_KEYS = new Set(["code", "content_text", "student_message"]);
const SENSITIVE_HEADERS = new Set(["x-aporia-device", "authorization", "cookie"]);

/** Recursively replaces the value of every sensitive key (case-insensitive). Does not mutate. */
export function scrub<T>(value: T): T {
  if (Array.isArray(value)) return value.map((item) => scrub(item)) as T;
  if (typeof value === "object" && value !== null) {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value as Record<string, unknown>)) {
      out[key] = SENSITIVE_KEYS.has(key.toLowerCase()) ? FILTERED : scrub(item);
    }
    return out as T;
  }
  return value;
}

interface Scrubbable {
  request?: {
    data?: unknown;
    cookies?: unknown;
    query_string?: unknown;
    headers?: Record<string, string>;
  };
}

/** `beforeSend`: no request bodies, no sensitive fields, no identifying headers. */
export function beforeSend<E extends Scrubbable>(event: E): E {
  const cleaned = scrub(event);
  const request = cleaned.request;
  if (request) {
    delete request.data; // the body of a hint request is the student's code
    delete request.cookies;
    delete request.query_string;
    if (request.headers) {
      request.headers = Object.fromEntries(
        Object.entries(request.headers).map(([k, v]) => [
          k,
          SENSITIVE_HEADERS.has(k.toLowerCase()) ? FILTERED : v,
        ]),
      );
    }
  }
  return cleaned;
}

export interface SentryLike {
  init: (options: Record<string, unknown>) => unknown;
  globalHandlersIntegration: () => unknown;
  dedupeIntegration: () => unknown;
}

/**
 * Initialises Sentry iff a DSN is configured. Returns whether it is active. The SDK is loaded
 * lazily, so builds without a DSN do not ship it (the background runs as a module worker).
 */
export async function initSentry(dsn: string | undefined, sentry?: SentryLike): Promise<boolean> {
  if (!dsn) return false;
  const sdk: SentryLike = sentry ?? ((await import("@sentry/browser")) as unknown as SentryLike);
  sdk.init({
    dsn,
    sendDefaultPii: false,
    tracesSampleRate: 0,
    // Only uncaught errors: no console, fetch or DOM breadcrumbs that could carry page content.
    defaultIntegrations: false,
    integrations: [sdk.globalHandlersIntegration(), sdk.dedupeIntegration()],
    beforeSend,
  });
  return true;
}
