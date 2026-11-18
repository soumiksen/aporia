import { beforeEach, describe, expect, it } from "vitest";
import { useHintStore } from "./hint-store";

describe("hint store", () => {
  beforeEach(() => useHintStore.getState().reset());
  it("streams then finishes", () => {
    const s = useHintStore.getState();
    s.start(1);
    s.append("a");
    s.append("b");
    expect(useHintStore.getState()).toMatchObject({ status: "streaming", text: "ab" });
    useHintStore.getState().finish();
    expect(useHintStore.getState().status).toBe("done");
  });
  it("records errors and resets", () => {
    useHintStore.getState().fail("network", "down");
    expect(useHintStore.getState()).toMatchObject({ status: "error", errorCode: "network" });
    useHintStore.getState().reset();
    expect(useHintStore.getState().status).toBe("idle");
  });
});
