import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "../src/api/client";
import { ApprovalDialog } from "../src/components/ApprovalDialog";
import { ErrorState, EmptyState, Skeleton } from "../src/components/States";

describe("shared interface states", () => {
  it("renders loading, empty, and offline states without invented records", () => {
    const { rerender } = render(<Skeleton rows={2} />);
    expect(screen.getByLabelText("Loading").children).toHaveLength(2);
    rerender(<EmptyState title="No jobs" detail="No jobs have been submitted in this room." />);
    expect(screen.getByText("No jobs have been submitted in this room.")).toBeVisible();
    rerender(<ErrorState error={new ApiError("Application API is unreachable.", 0)} />);
    expect(screen.getByText("Application API unavailable")).toBeVisible();
  });

  it("requires an explicit approval or rejection decision", () => {
    const submit = vi.fn();
    render(<ApprovalDialog open toolId="sha256" argumentsValue={{ value: "x" }} inputIds={[]} writeScopes={[]} reason="Owner review" pending={false} onClose={vi.fn()} onSubmit={submit} />);
    fireEvent.change(screen.getByLabelText("Decision note"), { target: { value: "Checked input" } });
    fireEvent.click(screen.getByRole("button", { name: "Approve action" }));
    expect(submit).toHaveBeenCalledWith({ decision: "approved", reason: "Checked input" });
  });
});
