import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Mascot } from "./Mascot";
import { NudgeBubble } from "./NudgeBubble";
import { Panel } from "./Panel";
import { StuckLabelPrompt } from "./StuckLabelPrompt";

describe("NudgeBubble", () => {
  it("asks 'Stuck? Want a nudge?' and wires each button to its own handler", async () => {
    const h = { onYes: vi.fn(), onNotNow: vi.fn(), onNever: vi.fn() };
    render(<NudgeBubble {...h} />);
    expect(screen.getByText("Stuck? Want a nudge?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    expect(h.onYes).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Not now" }));
    expect(h.onNotNow).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Never on this problem" }));
    expect(h.onNever).toHaveBeenCalledTimes(1);
    expect(h.onYes).toHaveBeenCalledTimes(1);
  });
});

describe("StuckLabelPrompt", () => {
  it("reports Yes and No", async () => {
    const onAnswer = vi.fn();
    render(<StuckLabelPrompt onAnswer={onAnswer} />);
    expect(screen.getByText("Were you actually stuck?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yes" }));
    await userEvent.click(screen.getByRole("button", { name: "No" }));
    expect(onAnswer.mock.calls).toEqual([[true], [false]]);
  });
});

describe("attentive mascot and reduced motion", () => {
  it("only animates under motion-safe, so prefers-reduced-motion users get no animation", () => {
    const { container } = render(<Mascot mood="attentive" />);
    const cls = container.querySelector("svg")?.getAttribute("class") ?? "";
    expect(cls).toContain("motion-safe:animate-bounce");
    expect(cls.split(" ").filter((c) => c.startsWith("animate-"))).toEqual([]);
  });
  it("is still for every other mood", () => {
    for (const mood of ["idle", "thinking", "happy", "error"] as const) {
      const { container, unmount } = render(<Mascot mood={mood} />);
      expect(container.querySelector("svg")?.getAttribute("class") ?? "").not.toContain("animate");
      unmount();
    }
  });
});

describe("Panel bubble slot", () => {
  it("shows the bubble above the mascot only while the panel is collapsed", () => {
    const bubble = <p>nudge here</p>;
    const { rerender } = render(
      <Panel open={false} onOpenChange={() => undefined} bubble={bubble} />,
    );
    expect(screen.getByText("nudge here")).toBeInTheDocument();
    rerender(<Panel open onOpenChange={() => undefined} bubble={bubble} />);
    expect(screen.queryByText("nudge here")).toBeNull();
  });
});
