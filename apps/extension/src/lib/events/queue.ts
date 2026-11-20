import { parseEvent } from "./schema";
import type { AporiaEvent } from "./types";

export const FLUSH_INTERVAL_MS = 30_000;
export const FLUSH_AT = 20;
export const MAX_BATCH = 50;
export const BACKOFF_MS = [1_000, 2_000] as const; // waits before attempts 2 and 3
export const MAX_ATTEMPTS = 3;
export const QUEUE_STORAGE_KEY = "aporiaEventQueue";

export interface QueueStorage {
  get(key: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
}

export interface EventQueueOptions {
  /** Checked on every enqueue and again at flush time: revoking consent drops what is queued. */
  isEnabled: () => Promise<boolean> | boolean;
  send: (events: AporiaEvent[]) => Promise<boolean>;
  storage?: QueueStorage;
  sleep?: (ms: number) => Promise<void>;
  setTimer?: (fn: () => void, ms: number) => unknown;
  clearTimer?: (handle: unknown) => void;
}

/**
 * Batches telemetry in the service worker: flush every 30 s or at 20 events, retry with backoff,
 * drop a batch after 3 failed attempts. Events are validated against the strict allowlist before
 * they are queued, and nothing is queued unless the student has opted in.
 */
export class EventQueue {
  private events: AporiaEvent[] = [];
  private timer: unknown = null;
  private flushing: Promise<void> | null = null;
  private readonly sleep: (ms: number) => Promise<void>;
  private readonly setTimer: (fn: () => void, ms: number) => unknown;
  private readonly clearTimer: (handle: unknown) => void;

  constructor(private readonly options: EventQueueOptions) {
    this.sleep = options.sleep ?? ((ms) => new Promise((r) => setTimeout(r, ms)));
    this.setTimer = options.setTimer ?? ((fn, ms) => setTimeout(fn, ms));
    this.clearTimer =
      options.clearTimer ?? ((h) => clearTimeout(h as ReturnType<typeof setTimeout>));
  }

  get size(): number {
    return this.events.length;
  }

  /** Restores a queue persisted before the service worker was stopped. */
  async load(): Promise<void> {
    if (!this.options.storage) return;
    try {
      const stored = (await this.options.storage.get(QUEUE_STORAGE_KEY))[QUEUE_STORAGE_KEY];
      if (Array.isArray(stored)) {
        const valid = stored.map(parseEvent).filter((e): e is AporiaEvent => e !== null);
        this.events = [...valid, ...this.events];
      }
    } catch {
      /* nothing to restore */
    }
    if (this.events.length > 0) this.schedule();
  }

  /** Returns true if the event was queued. Off, invalid or unknown-field events are dropped. */
  async enqueue(input: unknown): Promise<boolean> {
    if (!(await this.options.isEnabled())) return false;
    const event = parseEvent(input);
    if (!event) return false;
    this.events.push(event);
    await this.persist();
    if (this.events.length >= FLUSH_AT) {
      void this.flush();
    } else {
      this.schedule();
    }
    return true;
  }

  /** Drops everything queued (consent revoked). */
  async clear(): Promise<void> {
    this.events = [];
    if (this.timer !== null) this.clearTimer(this.timer);
    this.timer = null;
    await this.persist();
  }

  flush(): Promise<void> {
    if (this.flushing) return this.flushing;
    this.flushing = this.run().finally(() => {
      this.flushing = null;
    });
    return this.flushing;
  }

  private schedule(): void {
    if (this.timer !== null) return;
    this.timer = this.setTimer(() => {
      this.timer = null;
      void this.flush();
    }, FLUSH_INTERVAL_MS);
  }

  private async persist(): Promise<void> {
    try {
      await this.options.storage?.set({ [QUEUE_STORAGE_KEY]: this.events });
    } catch {
      /* persistence is best effort */
    }
  }

  private async run(): Promise<void> {
    if (this.timer !== null) this.clearTimer(this.timer);
    this.timer = null;
    while (this.events.length > 0) {
      if (!(await this.options.isEnabled())) {
        await this.clear(); // consent was revoked while events were waiting
        return;
      }
      const batch = this.events.slice(0, MAX_BATCH);
      const sent = await this.sendWithRetry(batch);
      // Sent or dropped after 3 failures: either way these events leave the queue.
      this.events = this.events.slice(batch.length);
      await this.persist();
      if (!sent) break; // the server is struggling: wait for the next flush instead of hammering it
    }
    if (this.events.length > 0) this.schedule();
  }

  private async sendWithRetry(batch: AporiaEvent[]): Promise<boolean> {
    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
      if (attempt > 0)
        await this.sleep(BACKOFF_MS[attempt - 1] ?? BACKOFF_MS[BACKOFF_MS.length - 1]!);
      try {
        if (await this.options.send(batch)) return true;
      } catch {
        /* counted as a failed attempt */
      }
    }
    return false;
  }
}
