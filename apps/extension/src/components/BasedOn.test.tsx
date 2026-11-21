import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BasedOn } from "./BasedOn";
import { useHintStore } from "../store/hint-store";

describe("BasedOn", () => {
  it("shows a chip per source", () => {
    render(
      <BasedOn
        sources={[
          { type: "note", slug: "sliding-window", heading: "Idea" },
          { type: "note", slug: "two-pointers", heading: "Common mistakes" },
        ]}
      />,
    );
    expect(screen.getByText("Based on")).toBeTruthy();
    expect(screen.getByText("sliding window · Idea")).toBeTruthy();
    expect(screen.getByText("two pointers · Common mistakes")).toBeTruthy();
  });

  it("renders nothing without sources", () => {
    const { container } = render(<BasedOn sources={[]} />);
    expect(container.firstChild).toBeNull();
  });
});

describe("hint store sources", () => {
  it("keeps sources from the done event and clears them on start", () => {
    const store = useHintStore.getState();
    store.start(2);
    store.finish({ sources: [{ type: "note", slug: "stack", heading: "Idea" }] });
    expect(useHintStore.getState().sources).toHaveLength(1);
    useHintStore.getState().start(2);
    expect(useHintStore.getState().sources).toEqual([]);
  });
});
