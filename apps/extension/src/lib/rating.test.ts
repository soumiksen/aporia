import { describe, expect, it, vi } from "vitest";
import { postRating } from "./rating";

const base = { apiUrl: "http://api", deviceId: "dev-1", hintId: "h/1", rating: 1 };

describe("postRating", () => {
  it("posts the rating with the device header and encodes the id", async () => {
    const f = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(
      async () => new Response(null, { status: 204 }),
    );
    expect(await postRating({ ...base, fetchFn: f as unknown as typeof fetch })).toBe(true);
    const [url, init] = f.mock.calls[0] ?? [];
    expect(url).toBe("http://api/v1/hints/h%2F1/rating");
    expect(init?.method).toBe("POST");
    expect((init?.headers as Record<string, string>)["x-aporia-device"]).toBe("dev-1");
    expect(JSON.parse(String(init?.body))).toEqual({ rating: 1 });
  });
  it("returns false on a non-2xx response or a network error, without throwing", async () => {
    const notFound = (async () => new Response("no", { status: 404 })) as typeof fetch;
    expect(await postRating({ ...base, fetchFn: notFound })).toBe(false);
    const down = (async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;
    expect(await postRating({ ...base, fetchFn: down })).toBe(false);
  });
});
