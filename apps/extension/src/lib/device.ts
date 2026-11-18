const KEY = "aporiaDeviceId";

interface StorageArea {
  get(key: string): Promise<Record<string, unknown>>;
  set(items: Record<string, unknown>): Promise<void>;
}

/** Returns the random device UUID, creating and persisting it on first use. */
export async function getOrCreateDeviceId(storage: StorageArea): Promise<string> {
  const existing = (await storage.get(KEY))[KEY];
  if (typeof existing === "string" && existing.length > 0) return existing;
  const id = crypto.randomUUID();
  await storage.set({ [KEY]: id });
  return id;
}
