import type { AgentEvent, JsonValue } from "../types/api";

export type RailState = "submitted" | "allowed" | "approval" | "finalized" | "denied" | "rejected" | "failed" | "neutral";

export function eventRailState(event: AgentEvent): RailState {
  if (event.event_type === "action.allowed" || event.event_type === "action.approved" || event.event_type === "action.completed") return "allowed";
  if (event.event_type === "action.approval_required") return "approval";
  if (event.event_type === "action.denied" || event.event_type === "security.violation") return "denied";
  if (event.event_type === "action.rejected") return "rejected";
  if (event.event_type === "job.failed") return "failed";
  if (event.event_type === "job.completed") return "allowed";
  if (event.event_type === "job.created" || event.event_type === "job.accepted" || event.event_type === "action.proposed") return "submitted";
  return "neutral";
}

export function payloadRecord(event: AgentEvent): Record<string, JsonValue> {
  if (event.payload && typeof event.payload === "object" && !Array.isArray(event.payload)) return event.payload as Record<string, JsonValue>;
  return {};
}

export function eventActionId(event: AgentEvent): string | null {
  const value = payloadRecord(event).action_id;
  return typeof value === "string" ? value : null;
}
