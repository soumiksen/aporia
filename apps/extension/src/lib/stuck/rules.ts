// Transparent, pure stuck rules. No timers, no browser APIs: everything comes from the snapshot.

export type StuckReason =
  "consecutive_failures" | "repeated_failure" | "inactivity" | "low_progress";

export interface VerdictKey {
  /** LeetCode status message, e.g. "Wrong Answer". */
  status: string | null;
  testcase: string | null;
  accepted: boolean;
}

export interface Snapshot {
  /** When tracking of this problem began (page opened or slug changed). */
  trackingStartedAt: number;
  lastEditAt: number | null;
  lastRunAt: number | null;
  /** When the tab last became visible or the system last became active again. */
  resumedAt: number | null;
  consecutiveFailedSubmissions: number;
  /** The most recent verdicts, oldest first (the last two matter). */
  lastVerdicts: VerdictKey[];
  /** Characters changed within the last `lowProgressWindowMs`. */
  changedChars: number;
  /** Failed runs and submissions since tracking started. */
  failedRuns: number;
  tabVisible: boolean;
  systemIdle: boolean;
}

export interface StuckConfig {
  consecutiveFailures: number;
  inactivityMs: number;
  lowProgressChars: number;
  lowProgressWindowMs: number;
  lowProgressMinFailedRuns: number;
}

export const MINUTE = 60_000;

export const DEFAULT_STUCK_CONFIG: StuckConfig = {
  consecutiveFailures: 3,
  inactivityMs: 4 * MINUTE,
  lowProgressChars: 20,
  lowProgressWindowMs: 10 * MINUTE,
  lowProgressMinFailedRuns: 2,
};

export interface StuckResult {
  stuck: boolean;
  reason: StuckReason | null;
}

const NOT_STUCK: StuckResult = { stuck: false, reason: null };

/**
 * Stuck if any of (checked in this order):
 * 1. 3+ consecutive failed submissions;
 * 2. the same failing verdict and the same last testcase twice in a row;
 * 3. no edits and no runs for 4 minutes while the tab is visible and the system is not idle;
 * 4. fewer than 20 changed characters over 10 minutes, after at least 2 failed runs.
 */
export function evaluateStuck(snapshot: Snapshot, config: StuckConfig, now: number): StuckResult {
  if (snapshot.consecutiveFailedSubmissions >= config.consecutiveFailures) {
    return { stuck: true, reason: "consecutive_failures" };
  }

  const [previous, latest] = snapshot.lastVerdicts.slice(-2);
  if (
    previous &&
    latest &&
    !previous.accepted &&
    !latest.accepted &&
    latest.testcase !== null &&
    previous.testcase === latest.testcase &&
    previous.status === latest.status
  ) {
    return { stuck: true, reason: "repeated_failure" };
  }

  if (snapshot.tabVisible && !snapshot.systemIdle) {
    const lastActivity = Math.max(
      snapshot.trackingStartedAt,
      snapshot.lastEditAt ?? 0,
      snapshot.lastRunAt ?? 0,
      snapshot.resumedAt ?? 0,
    );
    if (now - lastActivity >= config.inactivityMs) {
      return { stuck: true, reason: "inactivity" };
    }
  }

  if (
    snapshot.failedRuns >= config.lowProgressMinFailedRuns &&
    now - snapshot.trackingStartedAt >= config.lowProgressWindowMs &&
    snapshot.changedChars < config.lowProgressChars
  ) {
    return { stuck: true, reason: "low_progress" };
  }

  return NOT_STUCK;
}
