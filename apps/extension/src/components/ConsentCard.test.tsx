import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ConsentCard } from "./ConsentCard";

describe("ConsentCard", () => {
  it("explains what is shared and reports the choice", async () => {
    const onChoose = vi.fn();
    render(<ConsentCard onChoose={onChoose} />);
    expect(screen.getByText(/Share anonymous usage events/)).toBeInTheDocument();
    expect(screen.getByText(/Never your code or the problem text/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Allow" }));
    await userEvent.click(screen.getByRole("button", { name: "No thanks" }));
    expect(onChoose.mock.calls).toEqual([[true], [false]]);
  });
});
