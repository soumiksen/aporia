// First-party telemetry events. Strict allowlist: no code, no problem text, no free-form fields.

export const EVENT_TYPES = [
  "stuck_prompt_shown",
  "stuck_prompt_accepted",
  "stuck_prompt_dismissed",
  "hint_requested",
  "hint_rated",
  "stuck_label",
] as const;

export type EventType = (typeof EVENT_TYPES)[number];

export type DismissReason =
  "consecutive_failures" | "repeated_failure" | "inactivity" | "low_progress";

export interface AporiaEvent {
  type: EventType;
  /** epoch milliseconds */
  ts: number;
  slug?: string;
  level?: number;
  /** why the stuck detector fired */
  reason?: DismissReason;
  rating?: number;
  was_stuck?: boolean;
}

export type EventInput = Omit<AporiaEvent, "ts">;
