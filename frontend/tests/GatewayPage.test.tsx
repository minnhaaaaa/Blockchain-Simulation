import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { ApiProvider } from "../src/api/ApiContext";
import { GatewayPage } from "../src/pages/GatewayPage";

describe("room gateway", () => {
  beforeEach(() => localStorage.clear());

  it("keeps runtime connection and room values operator-controlled", async () => {
    const user = userEvent.setup();
    render(<MemoryRouter><ApiProvider><GatewayPage /></ApiProvider></MemoryRouter>);
    expect(screen.getByLabelText(/Application API URL/)).toHaveValue("");
    expect(screen.getByLabelText(/Room ID/)).toHaveValue("");

    await user.click(screen.getByRole("tab", { name: "Create room" }));
    expect(screen.getByLabelText("Protocol version")).toBeVisible();
    expect(screen.getByRole("button", { name: /Review, sign, and create room/ })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Generate" }));
    expect((screen.getByLabelText(/Room ID/) as HTMLInputElement).value).toMatch(/^room-[0-9a-f]{24}$/);
  });
});
