// Telemetry consent. Default: undecided and off. Nothing is queued unless `enabled` is true.

export const CONSENT_STORAGE_KEY = "aporiaConsent";

export interface Consent {
  /** false until the student has answered the first-run card or toggled the option. */
  decided: boolean;
  enabled: boolean;
}

export const DEFAULT_CONSENT: Consent = { decided: false, enabled: false };

export interface ConsentStorage {
  get(key: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
}

function isConsent(value: unknown): value is Consent {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.decided === "boolean" && typeof v.enabled === "boolean";
}

export async function getConsent(storage: ConsentStorage): Promise<Consent> {
  try {
    const value = (await storage.get(CONSENT_STORAGE_KEY))[CONSENT_STORAGE_KEY];
    return isConsent(value)
      ? { ...value, enabled: value.decided && value.enabled }
      : DEFAULT_CONSENT;
  } catch {
    return DEFAULT_CONSENT; // unreadable storage means no consent
  }
}

export async function setConsent(storage: ConsentStorage, enabled: boolean): Promise<Consent> {
  const consent: Consent = { decided: true, enabled };
  try {
    await storage.set({ [CONSENT_STORAGE_KEY]: consent });
  } catch {
    return DEFAULT_CONSENT; // could not persist: stay off
  }
  return consent;
}
