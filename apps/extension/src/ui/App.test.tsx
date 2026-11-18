import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HintEvent } from "@/lib/messages";
import { pageStore, resetPageState } from "@/lib/page-state";
import { useHintStore } from "@/store/hint-store";

type Listener = (m: { data: { requestId: string; event: HintEvent } }) => void;
const h = vi.hoisted(() => ({
  listener: null as null | ((m: unknown) => void),
  sendMessage: vi.fn<(type: string, data?: unknown) => Promise<undefined>>(async () => undefined),
}));

vi.mock("@/lib/protocol", () => ({
  sendMessage: h.sendMessage,
  onMessage: (_type: string, cb: (m: unknown) => void) => {
    h.listener = cb;
    return () => {
      h.listener = null;
    };
  },
}));

import { App } from "./App";

function emit(event: HintEvent) {
  const call = h.sendMessage.mock.calls.find((c) => c[0] === "getHint");
  const requestId = (call?.[1] as { requestId: string }).requestId;
  act(() => (h.listener as Listener)({ data: { requestId, event } }));
}

describe("App", () => {
  beforeEach(() => {
    h.sendMessage.mockClear();
    useHintStore.getState().reset();
    resetPageState(null);
  });

  it("shows a prompt to open a problem on non-problem pages and sends nothing", async () => {
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /ask aporia/i }));
    expect(screen.getByText("Open a problem to get started.")).toBeInTheDocument();
    expect(h.sendMessage).not.toHaveBeenCalled();
  });

  it("sends getHint with the latest bridge state and streams text", async () => {
    resetPageState("two-sum");
    pageStore.setState({ code: "def f(): pass", language: "python3" });
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /ask aporia/i }));
    const call = h.sendMessage.mock.calls.find((c) => c[0] === "getHint");
    const payload = call?.[1] as { request: { code: string; language: string; level: number } };
    expect(payload.request).toMatchObject({ code: "def f(): pass", language: "python3", level: 1 });
    emit({ event: "token", text: "What " });
    emit({ event: "token", text: "now?" });
    expect(screen.getByTestId("hint-view")).toHaveTextContent("What now?");
    emit({ event: "done", hint_id: "h", level: 1, sources: [] });
    expect(useHintStore.getState().status).toBe("done");
  });

  it("still sends with empty code and tells the user", async () => {
    resetPageState("two-sum");
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /ask aporia/i }));
    const call = h.sendMessage.mock.calls.find((c) => c[0] === "getHint");
    expect((call?.[1] as { request: { code: string } }).request.code).toBe("");
    expect(screen.getByRole("note")).toHaveTextContent("hasn't captured your code");
  });

  it("shows a clear error when the API is unreachable and can retry", async () => {
    resetPageState("two-sum");
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /ask aporia/i }));
    emit({ event: "error", code: "network", message: "Could not reach the Aporia server." });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not reach the Aporia server.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(h.sendMessage.mock.calls.filter((c) => c[0] === "getHint")).toHaveLength(2);
  });

  it("cancels when the panel is closed mid-stream", async () => {
    resetPageState("two-sum");
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /ask aporia/i }));
    await userEvent.click(screen.getByRole("button", { name: "Close panel" }));
    expect(h.sendMessage.mock.calls.some((c) => c[0] === "cancelHint")).toBe(true);
    expect(useHintStore.getState().status).toBe("idle");
  });

  it("resets the hint when the problem changes", async () => {
    resetPageState("two-sum");
    render(<App />);
    await userEvent.click(screen.getByRole("button", { name: /ask aporia/i }));
    emit({ event: "token", text: "old" });
    act(() => resetPageState("three-sum"));
    expect(useHintStore.getState()).toMatchObject({ status: "idle", text: "" });
  });
});
