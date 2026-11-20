import { describe, expect, it, vi } from "vitest";
import {
  CONSENT_STORAGE_KEY,
  DEFAULT_CONSENT,
  getConsent,
  setConsent,
  type ConsentStorage,
} from "../consent";
import { postEvents } from "./post";
import {
  BACKOFF_MS,
  EventQueue,
  FLUSH_AT,
  FLUSH_INTERVAL_MS,
  MAX_ATTEMPTS,
  MAX_BATCH,
  QUEUE_STORAGE_KEY,
  type QueueStorage,
} from "./queue";
import { parseEvent } from "./schema";
import type { AporiaEvent } from "./types";

const CANARY = "CANARY_STUDENT_CODE_8841";

function memory(): ConsentStorage & QueueStorage & { data: Record<string, unknown> } {
  const data: Record<string, unknown> = {};
  return {
    data,
    get: async (key) => ({ [key]: data[key] }),
    set: async (items) => void Object.assign(data, items),
  };
}

const ev = (over: Partial<AporiaEvent> = {}): AporiaEvent => ({
  type: "hint_requested",
  ts: 1_700_000_000_000,
  slug: "two-sum",
  level: 1,
  ...over,
});

function makeQueue(enabled: boolean | (() => boolean) = true) {
  const sent: AporiaEvent[][] = [];
  const sends = vi.fn(async (events: AporiaEvent[]) => {
    sent.push(events);
    return true;
  });
  const sleeps: number[] = [];
  const timers: { fn: () => void; ms: number; cleared: boolean }[] = [];
  const storage = memory();
  const queue = new EventQueue({
    isEnabled: typeof enabled === "function" ? enabled : () => enabled,
    send: sends,
    storage,
    sleep: async (ms) => void sleeps.push(ms),
    setTimer: (fn, ms) => {
      const t = { fn, ms, cleared: false };
      timers.push(t);
      return t;
    },
    clearTimer: (h) => void ((h as { cleared: boolean }).cleared = true),
  });
  return { queue, sends, sent, sleeps, timers, storage };
}

describe("consent", () => {
  it("is undecided and off by default", async () => {
    expect(await getConsent(memory())).toEqual(DEFAULT_CONSENT);
    expect(DEFAULT_CONSENT).toEqual({ decided: false, enabled: false });
  });
  it("persists the choice", async () => {
    const s = memory();
    expect(await setConsent(s, true)).toEqual({ decided: true, enabled: true });
    expect(await getConsent(s)).toEqual({ decided: true, enabled: true });
    expect(await setConsent(s, false)).toEqual({ decided: true, enabled: false });
    expect(await getConsent(s)).toEqual({ decided: true, enabled: false });
  });
  it("treats corrupt or unreadable storage as no consent", async () => {
    const s = memory();
    s.data[CONSENT_STORAGE_KEY] = { decided: false, enabled: true }; // inconsistent: not decided
    expect((await getConsent(s)).enabled).toBe(false);
    s.data[CONSENT_STORAGE_KEY] = "yes";
    expect(await getConsent(s)).toEqual(DEFAULT_CONSENT);
    const broken: ConsentStorage = {
      get: async () => {
        throw new Error("x");
      },
      set: async () => {
        throw new Error("x");
      },
    };
    expect(await getConsent(broken)).toEqual(DEFAULT_CONSENT);
    expect(await setConsent(broken, true)).toEqual(DEFAULT_CONSENT); // could not persist: off
  });
});

describe("event schema (strict allowlist)", () => {
  it("accepts the six event types with their typed fields", () => {
    const events: AporiaEvent[] = [
      ev({ type: "stuck_prompt_shown", reason: "inactivity", level: undefined }),
      ev({ type: "stuck_prompt_accepted" }),
      ev({ type: "stuck_prompt_dismissed", reason: "low_progress" }),
      ev({ type: "hint_requested", level: 3 }),
      ev({ type: "hint_rated", rating: 5 }),
      ev({ type: "stuck_label", was_stuck: false }),
    ];
    for (const e of events)
      expect(parseEvent(JSON.parse(JSON.stringify(e)))).toEqual(JSON.parse(JSON.stringify(e)));
  });
  it("rejects unknown types and every unknown field (a canary never gets through)", () => {
    expect(parseEvent({ ...ev(), type: "page_view" })).toBeNull();
    for (const field of ["code", "content_text", "student_message", "text", "anything"]) {
      expect(parseEvent({ ...ev(), [field]: CANARY })).toBeNull();
    }
  });
  it("rejects values that could carry free text or are out of range", () => {
    expect(parseEvent({ ...ev(), slug: CANARY })).toBeNull();
    expect(parseEvent({ ...ev(), reason: CANARY })).toBeNull();
    expect(parseEvent({ ...ev(), level: 9 })).toBeNull();
    expect(parseEvent({ ...ev(), rating: 0 })).toBeNull();
    expect(parseEvent({ ...ev(), ts: "now" })).toBeNull();
    expect(parseEvent(null)).toBeNull();
  });
});

describe("EventQueue", () => {
  it("queues nothing while consent is off", async () => {
    const { queue, sends, timers, storage } = makeQueue(false);
    for (let i = 0; i < 40; i += 1) expect(await queue.enqueue(ev())).toBe(false);
    expect(queue.size).toBe(0);
    expect(sends).not.toHaveBeenCalled();
    expect(timers).toHaveLength(0); // no flush timer either
    expect(storage.data[QUEUE_STORAGE_KEY]).toBeUndefined(); // nothing written to storage
  });

  it("drops events with unknown fields before they are queued", async () => {
    const { queue } = makeQueue();
    expect(await queue.enqueue({ ...ev(), code: CANARY })).toBe(false);
    expect(await queue.enqueue(ev())).toBe(true);
    await queue.flush();
    expect(queue.size).toBe(0);
  });

  it("sends a canary-free payload even if a caller passes extra fields", async () => {
    const { queue, sent } = makeQueue();
    await queue.enqueue({ ...ev(), code: CANARY, content_text: CANARY });
    await queue.enqueue(ev());
    await queue.flush();
    expect(JSON.stringify(sent)).not.toContain(CANARY);
    expect(sent.flat()).toHaveLength(1);
  });

  it("flushes after 30 seconds", async () => {
    const { queue, sent, timers } = makeQueue();
    await queue.enqueue(ev());
    await queue.enqueue(ev({ level: 2 }));
    expect(sent).toHaveLength(0);
    expect(timers).toHaveLength(1); // a single timer, not one per event
    expect(timers[0]?.ms).toBe(FLUSH_INTERVAL_MS);
    timers[0]?.fn();
    await queue.flush();
    expect(sent).toHaveLength(1);
    expect(sent[0]).toHaveLength(2);
  });

  it("flushes as soon as 20 events are waiting", async () => {
    const { queue, sent } = makeQueue();
    for (let i = 0; i < FLUSH_AT - 1; i += 1) await queue.enqueue(ev());
    expect(sent).toHaveLength(0);
    await queue.enqueue(ev());
    await queue.flush();
    expect(sent).toHaveLength(1);
    expect(sent[0]).toHaveLength(20);
    expect(queue.size).toBe(0);
  });

  it("never sends more than 50 events per request", async () => {
    const { queue, sent } = makeQueue();
    const q = queue as unknown as { events: AporiaEvent[] };
    q.events = Array.from({ length: 120 }, () => ev());
    await queue.flush();
    expect(sent.map((b) => b.length)).toEqual([50, 50, 20]);
    expect(MAX_BATCH).toBe(50);
  });

  it("retries with backoff and delivers on the third attempt", async () => {
    const { queue, sends, sleeps } = makeQueue();
    sends.mockResolvedValueOnce(false).mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    await queue.enqueue(ev());
    await queue.flush();
    expect(sends).toHaveBeenCalledTimes(3);
    expect(sleeps).toEqual([...BACKOFF_MS]);
    expect(queue.size).toBe(0);
  });

  it("drops the batch after 3 failed attempts and does not hammer the server", async () => {
    const { queue, sends } = makeQueue();
    sends.mockResolvedValue(false);
    await queue.enqueue(ev());
    await queue.flush();
    expect(sends).toHaveBeenCalledTimes(MAX_ATTEMPTS);
    expect(queue.size).toBe(0); // dropped
    await queue.flush();
    expect(sends).toHaveBeenCalledTimes(MAX_ATTEMPTS); // nothing left to send
  });

  it("counts a thrown error as a failed attempt", async () => {
    const { queue, sends } = makeQueue();
    sends.mockRejectedValue(new Error("network"));
    await queue.enqueue(ev());
    await queue.flush();
    expect(sends).toHaveBeenCalledTimes(3);
    expect(queue.size).toBe(0);
  });

  it("revoking consent while events wait drops them without sending", async () => {
    let enabled = true;
    const { queue, sends } = makeQueue(() => enabled);
    await queue.enqueue(ev());
    enabled = false;
    await queue.flush();
    expect(sends).not.toHaveBeenCalled();
    expect(queue.size).toBe(0);
  });

  it("clear() empties the queue, its storage and its timer", async () => {
    const { queue, timers, storage } = makeQueue();
    await queue.enqueue(ev());
    await queue.clear();
    expect(queue.size).toBe(0);
    expect(timers[0]?.cleared).toBe(true);
    expect(storage.data[QUEUE_STORAGE_KEY]).toEqual([]);
  });

  it("survives a service-worker restart by reloading the persisted queue", async () => {
    const first = makeQueue();
    await first.queue.enqueue(ev());
    await first.queue.enqueue(ev({ level: 3 }));
    const second = makeQueue();
    Object.assign(second.storage.data, first.storage.data);
    await second.queue.load();
    expect(second.queue.size).toBe(2);
    expect(second.timers).toHaveLength(1); // scheduled to flush
    // corrupt entries in storage are ignored
    second.storage.data[QUEUE_STORAGE_KEY] = [ev(), { type: "evil", code: CANARY }];
    const third = makeQueue();
    Object.assign(third.storage.data, second.storage.data);
    await third.queue.load();
    expect(third.queue.size).toBe(1);
  });
});

describe("postEvents", () => {
  const base = { apiUrl: "http://api", deviceId: "dev", events: [ev()] };
  it("posts a batch with the device header", async () => {
    const f = vi.fn<(u: string, i: RequestInit) => Promise<Response>>(
      async () => new Response(JSON.stringify({ accepted: 1 }), { status: 202 }),
    );
    expect(await postEvents({ ...base, fetchFn: f as unknown as typeof fetch })).toBe(true);
    const [url, init] = f.mock.calls[0] ?? [];
    expect(url).toBe("http://api/v1/events");
    expect((init?.headers as Record<string, string>)["x-aporia-device"]).toBe("dev");
    expect(JSON.parse(String(init?.body))).toEqual({ events: base.events });
  });
  it("retries on 5xx, 429 and network errors, but not on a rejected batch (4xx)", async () => {
    const status = (code: number) =>
      (async () => new Response(null, { status: code })) as typeof fetch;
    expect(await postEvents({ ...base, fetchFn: status(503) })).toBe(false);
    expect(await postEvents({ ...base, fetchFn: status(429) })).toBe(false);
    expect(await postEvents({ ...base, fetchFn: status(422) })).toBe(true); // invalid: drop, do not retry
    const down = (async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;
    expect(await postEvents({ ...base, fetchFn: down })).toBe(false);
  });
});
