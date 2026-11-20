import {
  DEFAULT_STUCK_CONFIG,
  evaluateStuck,
  type Snapshot,
  type StuckConfig,
  type StuckResult,
  type VerdictKey,
} from "./rules";

export interface VerdictSignal {
  phase: "run" | "submit";
  statusMessage: string | null;
  lastTestcase: string | null;
}

interface Edit {
  at: number;
  chars: number;
}

const MAX_VERDICTS_KEPT = 4;

/** Approximate number of changed characters: what remains after trimming the common prefix/suffix. */
export function changedCharacters(before: string, after: string): number {
  if (before === after) return 0;
  const max = Math.min(before.length, after.length);
  let prefix = 0;
  while (prefix < max && before[prefix] === after[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < max - prefix &&
    before[before.length - 1 - suffix] === after[after.length - 1 - suffix]
  ) {
    suffix += 1;
  }
  return Math.max(before.length - prefix - suffix, after.length - prefix - suffix);
}

/**
 * Collects stuck signals for the current problem (bridge `code` and `verdict` messages, page
 * visibility, system idle) and keeps a rolling window of edits. The clock is injected so tests
 * can use fake time.
 */
export class StuckTracker {
  private startedAt: number;
  private previousCode: string | null = null;
  private edits: Edit[] = [];
  private lastEditAt: number | null = null;
  private lastRunAt: number | null = null;
  private resumedAt: number | null = null;
  private consecutiveFailedSubmissions = 0;
  private failedRuns = 0;
  private verdicts: VerdictKey[] = [];
  private tabVisible = true;
  private systemIdle = false;

  constructor(
    private readonly now: () => number = Date.now,
    private readonly config: StuckConfig = DEFAULT_STUCK_CONFIG,
  ) {
    this.startedAt = this.now();
  }

  /** Starts over, e.g. when the problem slug changes. Visibility and idle state are kept. */
  reset(): void {
    this.startedAt = this.now();
    this.previousCode = null;
    this.edits = [];
    this.lastEditAt = null;
    this.lastRunAt = null;
    this.resumedAt = null;
    this.consecutiveFailedSubmissions = 0;
    this.failedRuns = 0;
    this.verdicts = [];
  }

  /** The first code message is the baseline (the starter code), not an edit. */
  onCode(code: string): void {
    const at = this.now();
    if (this.previousCode !== null) {
      const chars = changedCharacters(this.previousCode, code);
      if (chars > 0) {
        this.edits.push({ at, chars });
        this.lastEditAt = at;
      }
    }
    this.previousCode = code;
    this.prune(at);
  }

  onVerdict(signal: VerdictSignal): void {
    const at = this.now();
    this.lastRunAt = at;
    const accepted = signal.statusMessage === "Accepted";
    // A missing status is unknown: it counts as a run but never as a failure.
    const failed = signal.statusMessage !== null && !accepted;
    if (failed) this.failedRuns += 1;
    if (signal.phase === "submit") {
      this.consecutiveFailedSubmissions = failed ? this.consecutiveFailedSubmissions + 1 : 0;
    }
    this.verdicts.push({
      status: signal.statusMessage,
      testcase: signal.lastTestcase,
      accepted,
    });
    if (this.verdicts.length > MAX_VERDICTS_KEPT) this.verdicts.shift();
  }

  setVisible(visible: boolean): void {
    if (visible && !this.tabVisible) this.resumedAt = this.now(); // hidden time is not inactivity
    this.tabVisible = visible;
  }

  setIdle(idle: boolean): void {
    if (!idle && this.systemIdle) this.resumedAt = this.now();
    this.systemIdle = idle;
  }

  snapshot(): Snapshot {
    const at = this.now();
    this.prune(at);
    return {
      trackingStartedAt: this.startedAt,
      lastEditAt: this.lastEditAt,
      lastRunAt: this.lastRunAt,
      resumedAt: this.resumedAt,
      consecutiveFailedSubmissions: this.consecutiveFailedSubmissions,
      lastVerdicts: [...this.verdicts],
      changedChars: this.edits.reduce((sum, e) => sum + e.chars, 0),
      failedRuns: this.failedRuns,
      tabVisible: this.tabVisible,
      systemIdle: this.systemIdle,
    };
  }

  evaluate(): StuckResult {
    return evaluateStuck(this.snapshot(), this.config, this.now());
  }

  private prune(at: number): void {
    const cutoff = at - this.config.lowProgressWindowMs;
    this.edits = this.edits.filter((e) => e.at > cutoff);
  }
}
