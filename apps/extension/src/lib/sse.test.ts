import { describe, expect, it, vi } from "vitest";
import type { HintEvent } from "./messages";
import { streamHint } from "./sse";

const request = {
  problem: { slug: "s", title: "t", difficulty: "Easy", tags: [], content_text: "", meta: null },
  code: "",
  language: "python",
};

function sse(chunks: string[], status = 200): Response {
  const enc = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(c) {
      chunks.forEach((x) => c.enqueue(enc.encode(x)));
      c.close();
    },
  });
  return new Response(body, { status, headers: { "content-type": "text/event-stream" } });
}

async function run(fetchFn: typeof fetch, signal?: AbortSignal): Promise<HintEvent[]> {
  const events: HintEvent[] = [];
  await streamHint({
    apiUrl: "http://api",
    deviceId: "dev-1",
    request,
    signal,
    fetchFn,
    onEvent: (e) => events.push(e),
  });
  return events;
}

describe("streamHint", () => {
  it("relays token and done events, across chunk boundaries", async () => {
    const f = vi.fn<(url: string, init: RequestInit) => Promise<Response>>(async () =>
      sse([
        'event: token\ndata: {"text":"Hel',
        'lo"}\n\nevent: token\ndata: {"text":" world"}\n\n',
        'event: done\ndata: {"hint_id":"h1","level":1,"sources":[]}\n\n',
      ]),
    );
    const events = await run(f as unknown as typeof fetch);
    expect(events).toEqual([
      { event: "token", text: "Hello" },
      { event: "token", text: " world" },
      { event: "done", hint_id: "h1", level: 1, sources: [] },
    ]);
    const init = f.mock.calls[0]?.[1] as RequestInit;
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>)["x-aporia-device"]).toBe("dev-1");
  });

  it("relays server error events", async () => {
    const events = await run((async () =>
      sse(['event: error\ndata: {"code":"llm","message":"boom"}\n\n'])) as unknown as typeof fetch);
    expect(events).toEqual([{ event: "error", code: "llm", message: "boom" }]);
  });

  it("maps non-200 responses to typed errors", async () => {
    const events = await run((async () => new Response("x", { status: 429 })) as typeof fetch);
    expect(events[0]).toMatchObject({ event: "error", code: "http_429" });
  });

  it("maps network failure to a network error", async () => {
    const events = await run((async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch);
    expect(events).toEqual([expect.objectContaining({ event: "error", code: "network" })]);
  });

  it("reports a truncated stream", async () => {
    const events = await run((async () =>
      sse(['event: token\ndata: {"text":"a"}\n\n'])) as unknown as typeof fetch);
    expect(events.at(-1)).toMatchObject({ event: "error", code: "stream_ended" });
  });

  it("is silent on abort", async () => {
    const ctrl = new AbortController();
    ctrl.abort();
    const events = await run(
      (async () => {
        throw new DOMException("aborted", "AbortError");
      }) as typeof fetch,
      ctrl.signal,
    );
    expect(events).toEqual([]);
  });

  it("ignores malformed events", async () => {
    const events = await run((async () =>
      sse([
        "event: token\ndata: not-json\n\n",
        'event: done\ndata: {"hint_id":"h","level":1,"sources":[]}\n\n',
      ])) as unknown as typeof fetch);
    expect(events).toEqual([{ event: "done", hint_id: "h", level: 1, sources: [] }]);
  });
});
