import { describe, expect, it } from "vitest";
import { getOrCreateDeviceId } from "./device";

function memoryStorage() {
  const data: Record<string, unknown> = {};
  return {
    get: async (k: string) => ({ [k]: data[k] }),
    set: async (items: Record<string, unknown>) => void Object.assign(data, items),
  };
}

describe("getOrCreateDeviceId", () => {
  it("creates once and then reuses the same uuid", async () => {
    const storage = memoryStorage();
    const a = await getOrCreateDeviceId(storage);
    const b = await getOrCreateDeviceId(storage);
    expect(a).toMatch(/^[0-9a-f-]{36}$/);
    expect(b).toBe(a);
  });
});
