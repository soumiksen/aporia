import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { HintActions } from "./HintActions";
import { LevelBadge } from "./LevelBadge";
import { StudentMessageBox } from "./StudentMessageBox";
import { UnsupportedBanner } from "./UnsupportedBanner";

describe("LevelBadge", () => {
  it.each([
    [1, "L1", "Nudge"],
    [2, "L2", "Hint"],
    [3, "L3", "Explanation"],
    [4, "L4", "Worked example"],
  ])("shows level %i", (level, short, label) => {
    render(<LevelBadge level={level} />);
    const badge = screen.getByTestId("level-badge");
    expect(badge).toHaveTextContent(short);
    expect(badge).toHaveAttribute("aria-label", `Hint level ${level} of 4: ${label}`);
  });
  it("clamps out-of-range levels", () => {
    render(<LevelBadge level={9} />);
    expect(screen.getByTestId("level-badge")).toHaveTextContent("L4");
  });
});

describe("HintActions", () => {
  const props = { rated: false, onBigger: vi.fn(), onNotHelpful: vi.fn() };

  it("renders nothing until a hint is done", () => {
    for (const status of ["idle", "streaming", "error"] as const) {
      const { container, unmount } = render(<HintActions {...props} status={status} level={1} />);
      expect(container).toBeEmptyDOMElement();
      unmount();
    }
  });
  it("escalates with the bigger-hint button", async () => {
    const onBigger = vi.fn();
    render(<HintActions {...props} onBigger={onBigger} status="done" level={2} />);
    await userEvent.click(screen.getByRole("button", { name: "Need a bigger hint" }));
    expect(onBigger).toHaveBeenCalledTimes(1);
  });
  it("disables escalation at the top level", () => {
    render(<HintActions {...props} status="done" level={4} />);
    expect(screen.getByRole("button", { name: "Need a bigger hint" })).toBeDisabled();
  });
  it("offers a not-helpful link that becomes a thank-you once rated", async () => {
    const onNotHelpful = vi.fn();
    const { rerender } = render(
      <HintActions {...props} onNotHelpful={onNotHelpful} status="done" level={1} />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Not helpful" }));
    expect(onNotHelpful).toHaveBeenCalledTimes(1);
    rerender(<HintActions {...props} rated status="done" level={1} />);
    expect(screen.queryByRole("button", { name: "Not helpful" })).toBeNull();
    expect(screen.getByRole("status")).toHaveTextContent("Thanks for the feedback");
  });
});

describe("UnsupportedBanner", () => {
  it("explains the limitation", () => {
    render(<UnsupportedBanner />);
    expect(screen.getByRole("note")).toHaveTextContent(
      "I can help with ideas but cannot run your code on this problem yet.",
    );
  });
});

describe("StudentMessageBox", () => {
  it("is limited to 300 characters and shows a counter", async () => {
    const onChange = vi.fn();
    const { rerender } = render(<StudentMessageBox value="" onChange={onChange} />);
    const box = screen.getByLabelText(/stuck on/i);
    expect(box).toHaveAttribute("maxlength", "300");
    await userEvent.type(box, "a");
    expect(onChange).toHaveBeenCalledWith("a");
    rerender(<StudentMessageBox value={"x".repeat(120)} onChange={onChange} />);
    expect(screen.getByText("120/300")).toBeInTheDocument();
  });
  it("truncates pasted text beyond the limit", () => {
    const onChange = vi.fn();
    render(<StudentMessageBox value="" onChange={onChange} />);
    // jsdom does not enforce maxlength for programmatic changes, so the handler must.
    fireEvent.change(screen.getByLabelText(/stuck on/i), { target: { value: "y".repeat(400) } });
    expect(onChange.mock.calls.at(-1)?.[0]).toHaveLength(300);
  });
});
