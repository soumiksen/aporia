// When may Aporia offer a nudge? Cooldown after any nudge, snooze after "Not now", and a
// persistent per-problem opt-out. Pure functions plus thin storage helpers.

export const COOLDOWN_MS = 10 * 60_000;
export const SNOOZE_MS = 30 * 60_000;
export const POLICY_STORAGE_KEY = "aporiaStuckPolicy";

export interface PolicyState {
  lastNudgeAt: number | null;
  snoozedUntil: number | null;
  disabledSlugs: string[];
}

export const EMPTY_POLICY: PolicyState = {
  lastNudgeAt: null,
  snoozedUntil: null,
  disabledSlugs: [],
};

export function shouldPrompt(now: number, state: PolicyState, slug: string | null): boolean {
  if (!slug || state.disabledSlugs.includes(slug)) return false;
  if (state.snoozedUntil !== null && now < state.snoozedUntil) return false;
  if (state.lastNudgeAt !== null && now - state.lastNudgeAt < COOLDOWN_MS) return false;
  return true;
}

/** Starts the cooldown. Call whenever a nudge is shown, whatever the student answers. */
export function recordNudgeShown(state: PolicyState, now: number): PolicyState {
  return { ...state, lastNudgeAt: now };
}

export function snooze(state: PolicyState, now: number): PolicyState {
  return { ...state, snoozedUntil: now + SNOOZE_MS };
}

export function disableSlug(state: PolicyState, slug: string): PolicyState {
  return state.disabledSlugs.includes(slug)
    ? state
    : { ...state, disabledSlugs: [...state.disabledSlugs, slug] };
}

export interface StorageArea {
  get(key: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
}

function isPolicy(value: unknown): value is PolicyState {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    (v.lastNudgeAt === null || typeof v.lastNudgeAt === "number") &&
    (v.snoozedUntil === null || typeof v.snoozedUntil === "number") &&
    Array.isArray(v.disabledSlugs) &&
    v.disabledSlugs.every((s) => typeof s === "string")
  );
}

export async function loadPolicy(storage: StorageArea): Promise<PolicyState> {
  try {
    const value = (await storage.get(POLICY_STORAGE_KEY))[POLICY_STORAGE_KEY];
    return isPolicy(value) ? value : EMPTY_POLICY;
  } catch {
    return EMPTY_POLICY;
  }
}

export async function savePolicy(storage: StorageArea, state: PolicyState): Promise<void> {
  try {
    await storage.set({ [POLICY_STORAGE_KEY]: state });
  } catch {
    /* storage unavailable: the policy simply is not persisted */
  }
}
