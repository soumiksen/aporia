import { describe, expect, it, vi } from "vitest";
import { FILTERED, beforeSend, initSentry, scrub } from "./sentry";

const CANARY = "CANARY_STUDENT_CODE_8841";
const STATEMENT = "CANARY_PROBLEM_TEXT_5520";

describe("scrub", () => {
  it("removes code, content_text and student_message at any depth, case-insensitively", () => {
    const event = {
      extra: { code: CANARY, keep: 1 },
      contexts: { hint: { problem: { content_text: STATEMENT, slug: "two-sum" } } },
      list: [{ student_message: CANARY }, { ok: true }, "plain"],
      UPPER: { CONTENT_TEXT: STATEMENT },
    };
    const cleaned = scrub(event);
    const dump = JSON.stringify(cleaned);
    expect(dump).not.toContain(CANARY);
    expect(dump).not.toContain(STATEMENT);
    expect(cleaned.extra).toEqual({ code: FILTERED, keep: 1 });
    expect(cleaned.contexts.hint.problem).toEqual({ content_text: FILTERED, slug: "two-sum" });
    expect(cleaned.list[1]).toEqual({ ok: true });
    expect(event.extra.code).toBe(CANARY); // input untouched
  });
  it("leaves primitives and null alone", () => {
    expect(scrub(5)).toBe(5);
    expect(scrub(null)).toBeNull();
    expect(scrub("code")).toBe("code");
  });
});

describe("beforeSend", () => {
  it("drops request bodies, cookies and identifying headers", () => {
    const cleaned = beforeSend({
      request: {
        url: "http://x/v1/hint",
        data: { code: CANARY, problem: { content_text: STATEMENT } },
        cookies: { s: "1" },
        query_string: "a=b",
        headers: { "X-Aporia-Device": "dev-uuid", "content-type": "application/json" },
      },
      extra: { student_message: CANARY },
    } as never);
    const dump = JSON.stringify(cleaned);
    expect(dump).not.toContain(CANARY);
    expect(dump).not.toContain(STATEMENT);
    expect(dump).not.toContain("dev-uuid");
    const request = (cleaned as { request: Record<string, unknown> }).request;
    expect(request.data).toBeUndefined();
    expect(request.cookies).toBeUndefined();
    expect(request.query_string).toBeUndefined();
    expect(request.url).toBe("http://x/v1/hint");
    expect((request.headers as Record<string, string>)["X-Aporia-Device"]).toBe(FILTERED);
    expect((request.headers as Record<string, string>)["content-type"]).toBe("application/json");
  });
  it("handles events without a request", () => {
    expect(beforeSend({ message: "x" } as never)).toEqual({ message: "x" });
  });
});

describe("initSentry", () => {
  const fake = () => ({
    init: vi.fn(),
    globalHandlersIntegration: () => "globalHandlers",
    dedupeIntegration: () => "dedupe",
  });
  it("does nothing without a DSN", async () => {
    const sentry = fake();
    expect(await initSentry(undefined, sentry)).toBe(false);
    expect(await initSentry("", sentry)).toBe(false);
    expect(sentry.init).not.toHaveBeenCalled();
  });
  it("initialises with the scrubber, no PII and no tracing when a DSN is set", async () => {
    const sentry = fake();
    expect(await initSentry("https://public@example.invalid/1", sentry)).toBe(true);
    const options = sentry.init.mock.calls[0]?.[0] as Record<string, unknown>;
    expect(options.dsn).toBe("https://public@example.invalid/1");
    expect(options.sendDefaultPii).toBe(false);
    expect(options.tracesSampleRate).toBe(0);
    expect(options.beforeSend).toBe(beforeSend);
    expect(options.defaultIntegrations).toBe(false); // no console/fetch/DOM breadcrumbs
    expect(options.integrations).toEqual(["globalHandlers", "dedupe"]);
  });
});
