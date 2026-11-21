import { describe, expect, it, vi } from "vitest";
import { postAttempt, verdictToReport } from "./attempt";

describe("verdictToReport", () => {
  it("reports only accepted submissions", () => {
    expect(verdictToReport({ phase: "submit", statusMessage: "Accepted" })).toBe("Accepted");
    expect(verdictToReport({ phase: "run", statusMessage: "Accepted" })).toBeNull();
    expect(verdictToReport({ phase: "submit", statusMessage: "Wrong Answer" })).toBeNull();
    expect(verdictToReport({ phase: "submit", statusMessage: null })).toBeNull();
  });
});

describe("postAttempt", () => {
  it("sends only slug and verdict", async () => {
    const fetchFn = vi.fn().mockResolvedValue({ ok: true });
    const ok = await postAttempt({
      apiUrl: "http://api",
      deviceId: "d1",
      slug: "two-sum",
      verdict: "Accepted",
      fetchFn,
    });
    expect(ok).toBe(true);
    const [url, init] = fetchFn.mock.calls[0] ?? [];
    expect(url).toBe("http://api/v1/attempts");
    expect(JSON.parse(init?.body)).toEqual({ slug: "two-sum", verdict: "Accepted" });
    expect(init?.headers["x-aporia-device"]).toBe("d1");
  });

  it("never throws", async () => {
    const fetchFn = vi.fn().mockRejectedValue(new Error("offline"));
    expect(
      await postAttempt({ apiUrl: "x", deviceId: "d", slug: "s", verdict: "Accepted", fetchFn }),
    ).toBe(false);
  });
});
