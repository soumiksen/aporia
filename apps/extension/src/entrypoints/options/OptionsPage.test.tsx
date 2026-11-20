import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

const h = vi.hoisted(() => ({
  consent: { decided: false, enabled: false },
  sendMessage: vi.fn(async (type: string, data?: { enabled: boolean }) => {
    if (type === "setConsent") h.consent = { decided: true, enabled: data?.enabled ?? false };
    return h.consent;
  }),
}));
vi.mock("@/lib/protocol", () => ({ sendMessage: h.sendMessage, onMessage: () => () => undefined }));

import { OptionsPage } from "./OptionsPage";

describe("OptionsPage", () => {
  it("shows the toggle off by default and sends the choice", async () => {
    render(<OptionsPage />);
    const box = await screen.findByRole("checkbox", { name: /Share anonymous usage events/ });
    await waitFor(() => expect(box).toBeEnabled());
    expect(box).not.toBeChecked();
    await userEvent.click(box);
    expect(h.sendMessage).toHaveBeenCalledWith("setConsent", { enabled: true });
    expect(box).toBeChecked();
    await userEvent.click(box);
    expect(h.sendMessage).toHaveBeenLastCalledWith("setConsent", { enabled: false });
  });
});
