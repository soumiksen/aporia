import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ErrorView } from "./ErrorView";
import { HintView } from "./HintView";

describe("HintView", () => {
  it("renders nothing when idle", () => {
    const { container } = render(<HintView status="idle" text="" />);
    expect(container).toBeEmptyDOMElement();
  });
  it("shows a thinking state before the first token", () => {
    render(<HintView status="streaming" text="" />);
    expect(screen.getByRole("status")).toHaveTextContent("Thinking");
  });
  it("renders streamed text in a polite live region", () => {
    const { container } = render(<HintView status="streaming" text="What happens" />);
    const live = container.querySelector('[aria-live="polite"]');
    expect(live).toHaveTextContent("What happens");
    expect(screen.queryByRole("status")).toBeNull();
  });
  it("renders final text without the cursor when done", () => {
    const { container } = render(<HintView status="done" text="Done text" />);
    expect(container).toHaveTextContent("Done text");
    expect(container.querySelector(".animate-pulse")).toBeNull();
  });
});

describe("ErrorView", () => {
  it("announces the error and offers retry", () => {
    render(<ErrorView message="API unreachable" onRetry={() => undefined} />);
    expect(screen.getByRole("alert")).toHaveTextContent("API unreachable");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });
});
