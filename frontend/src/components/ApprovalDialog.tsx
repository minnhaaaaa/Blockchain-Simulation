import { useEffect, useRef, useState } from "react";
import type { ActionDecisionRequest } from "../types/api";

export function ApprovalDialog({ open, toolId, argumentsValue, inputIds, writeScopes, reason, pending, onClose, onSubmit }: { open: boolean; toolId: string; argumentsValue: unknown; inputIds: string[]; writeScopes: string[]; reason: string; pending: boolean; onClose: () => void; onSubmit: (decision: ActionDecisionRequest) => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null); const approveRef = useRef<HTMLButtonElement>(null); const [decisionReason, setDecisionReason] = useState("");
  useEffect(() => { const dialog = dialogRef.current; if (open && dialog && !dialog.open) { dialog.showModal(); approveRef.current?.focus(); } else if (!open && dialog?.open) dialog.close(); }, [open]);
  return <dialog ref={dialogRef} className="approval-dialog" onCancel={event => { event.preventDefault(); onClose(); }} onClose={onClose}>
    <form method="dialog" onSubmit={event => event.preventDefault()}>
      <h2>Review requested action</h2><p>The action will not execute until you decide.</p>
      <dl className="definition-list"><dt>Tool</dt><dd className="mono">{toolId}</dd><dt>Policy reason</dt><dd>{reason}</dd><dt>Inputs</dt><dd>{inputIds.join(", ") || "None"}</dd><dt>Write scope</dt><dd>{writeScopes.join(", ") || "None"}</dd><dt>Arguments</dt><dd><pre>{JSON.stringify(argumentsValue, null, 2)}</pre></dd></dl>
      <label>Decision note <textarea value={decisionReason} onChange={event => setDecisionReason(event.target.value)} maxLength={1000} /></label>
      <footer><button type="button" className="button button-secondary" disabled={pending} onClick={() => onSubmit({ decision: "rejected", ...(decisionReason ? { reason: decisionReason } : {}) })}>Reject</button><button ref={approveRef} type="button" className="button button-primary" disabled={pending} onClick={() => onSubmit({ decision: "approved", ...(decisionReason ? { reason: decisionReason } : {}) })}>Approve action</button></footer>
    </form>
  </dialog>;
}
