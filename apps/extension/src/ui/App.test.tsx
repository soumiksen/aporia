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

function emit2(event: HintEvent) {
  const calls = h.sendMessage.mock.calls.filter((c) => c[0] === "getHint");
  const requestId = (calls.at(-1)?.[1] as { requestId: string }).requestId;
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
    emit({ event: "done", hint_id: "h", level: 1, sources: [], supported: true });
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

  describe("hint ladder", () => {
    const requests = () =>
      h.sendMessage.mock.calls
        .filter((c) => c[0] === "getHint")
        .map((c) => (c[1] as { request: Record<string, unknown> }).request);

    async function openAndFinish(level = 1, supported = true) {
      resetPageState("two-sum");
      pageStore.setState({ code: "x", language: "python3" });
      render(<App />);
      await userEvent.click(screen.getByRole("button", { name: /ask aporia/i }));
      emit({ event: "token", text: "Hmm?" });
      emit({ event: "done", hint_id: "hint-1", level, sources: [], supported });
    }

    it("shows the served level and asks for level + 1 with the typed message", async () => {
      await openAndFinish(1);
      expect(screen.getByTestId("level-badge")).toHaveTextContent("L1");
      await userEvent.type(screen.getByLabelText(/stuck on/i), "I do not get the loop");
      await userEvent.click(screen.getByRole("button", { name: "Need a bigger hint" }));
      const [first, second] = requests();
      expect(first).toMatchObject({ level: 1, student_message: null });
      expect(second).toMatchObject({ level: 2, student_message: "I do not get the loop" });
      expect(screen.getByLabelText(/stuck on/i)).toHaveValue(""); // cleared after sending
      emit2({ event: "done", hint_id: "hint-2", level: 2, sources: [], supported: true });
      expect(screen.getByTestId("level-badge")).toHaveTextContent("L2");
    });

    it("never asks above level 4 and disables the button there", async () => {
      await openAndFinish(4);
      expect(screen.getByRole("button", { name: "Need a bigger hint" })).toBeDisabled();
      expect(requests().every((r) => (r.level as number) <= 4)).toBe(true);
    });

    it("shows the unsupported banner only for unsupported problems", async () => {
      await openAndFinish(1, false);
      expect(screen.getByText(/cannot run your code on this problem yet/)).toBeInTheDocument();
    });

    it("hides the banner for supported problems", async () => {
      await openAndFinish(1, true);
      expect(screen.queryByText(/cannot run your code/)).toBeNull();
    });

    it("rates the hint once with 'Not helpful'", async () => {
      await openAndFinish(1);
      await userEvent.click(screen.getByRole("button", { name: "Not helpful" }));
      const ratings = h.sendMessage.mock.calls.filter((c) => c[0] === "rateHint");
      expect(ratings).toHaveLength(1);
      expect(ratings[0]?.[1]).toEqual({ hintId: "hint-1", rating: 1 });
      expect(screen.getByText("Thanks for the feedback")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: "Not helpful" })).toBeNull();
    });

    it("reports failed attempts since the last hint, then resets the counter", async () => {
      resetPageState("two-sum");
      pageStore.setState({
        code: "x",
        language: "python3",
        failedSinceHint: 3,
        lastVerdict: {
          phase: "submit",
          status: "11",
          statusMessage: "Wrong Answer",
          runtime: null,
          lastTestcase: null,
          expectedOutput: null,
          actualOutput: null,
        },
      });
      render(<App />);
      await userEvent.click(screen.getByRole("button", { name: /ask aporia/i }));
      expect(requests()[0]).toMatchObject({ failed_attempts: 3, last_verdict: "Wrong Answer" });
      expect(pageStore.getState().failedSinceHint).toBe(0);
    });

    it("keeps the typed message when retrying after an error", async () => {
      resetPageState("two-sum");
      render(<App />);
      await userEvent.click(screen.getByRole("button", { name: /ask aporia/i }));
      emit({ event: "error", code: "network", message: "down" });
      await userEvent.type(screen.getByLabelText(/stuck on/i), "stuck on line 3");
      await userEvent.click(screen.getByRole("button", { name: "Try again" }));
      expect(requests().at(-1)).toMatchObject({ student_message: "stuck on line 3" });
    });
  });
});
