import { AlertTriangle, CheckCircle2, CircleDashed, Clock3, ShieldAlert, WifiOff } from "lucide-react";
import { titleCase } from "../utils/format";

type Tone = "success" | "info" | "warning" | "danger" | "neutral";

function toneFor(value: string): Tone {
  if (["online", "connected", "ready", "allowed", "approved", "completed", "finalized", "success"].includes(value)) return "success";
  if (["submitted", "included", "running", "connecting", "configured"].includes(value)) return "info";
  if (["waiting_approval", "approval_required", "pending", "starting", "unconfigured"].includes(value)) return "warning";
  if (["denied", "rejected", "failed", "offline", "unavailable", "degraded"].includes(value)) return "danger";
  return "neutral";
}

export function StatusBadge({ value, label }: { value: string; label?: string }) {
  const tone = toneFor(value);
  const Icon = tone === "success" ? CheckCircle2 : tone === "danger" ? ShieldAlert : tone === "warning" ? Clock3 : tone === "info" ? CircleDashed : AlertTriangle;
  return <span className={`status-badge status-${tone}`}><Icon aria-hidden="true" size={14} />{label ?? titleCase(value)}</span>;
}

export function ConnectionBadge({ online }: { online: boolean }) {
  return <span className={`status-badge status-${online ? "success" : "danger"}`}>{online ? <CheckCircle2 size={14} /> : <WifiOff size={14} />}{online ? "API connected" : "API unavailable"}</span>;
}
