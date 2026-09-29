import { CheckCircle2, Play, UserCheck, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { useAcceptJob, useDecideAction, useJob, useRunJob } from "../api/hooks";
import { ApprovalDialog } from "../components/ApprovalDialog";
import { PageHeader } from "../components/AppShell";
import { Copyable } from "../components/Copyable";
import { ExecutionRail } from "../components/ExecutionRail";
import { Inspector } from "../components/Inspector";
import { ErrorState, Skeleton } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import type { Action, AgentEvent, Decision, JsonValue } from "../types/api";
import { eventActionId, payloadRecord } from "../utils/events";
import { formatTimestamp, shortId, titleCase } from "../utils/format";

function actionFromEvent(event: AgentEvent | undefined): Action | null { if (!event || event.event_type !== "action.proposed") return null; return payloadRecord(event) as unknown as Action; }
function decisionFromEvent(event: AgentEvent | undefined): Decision | null { if (!event || !event.event_type.startsWith("action.")) return null; const record=payloadRecord(event); return typeof record.decision === "string" ? record as unknown as Decision : null; }

export function JobDetailPage() {
  const {roomId="",jobId=""}=useParams(); const detail=useJob(roomId,jobId); const accept=useAcceptJob(roomId,jobId); const run=useRunJob(roomId,jobId); const [selected,setSelected]=useState<AgentEvent|null>(null); const [approvalOpen,setApprovalOpen]=useState(false);
  const pendingDecision=useMemo(()=>detail.data?.events.findLast(event=>event.event_type==="action.approval_required"&&!detail.data?.events.some(later=>later.sequence>event.sequence&&eventActionId(later)===eventActionId(event)&&["action.approved","action.rejected"].includes(later.event_type))),[detail.data]);
  const pendingActionId=pendingDecision?eventActionId(pendingDecision):null; const pendingProposal=useMemo(()=>detail.data?.events.find(event=>event.event_type==="action.proposed"&&eventActionId(event)===pendingActionId),[detail.data,pendingActionId]); const action=actionFromEvent(pendingProposal); const decision=decisionFromEvent(pendingDecision); const decide=useDecideAction(roomId,jobId,pendingActionId??"");
  if(detail.isPending)return <div className="page"><PageHeader title="Job detail"/><Skeleton rows={10}/></div>;
  if(detail.error)return <div className="page"><PageHeader title="Job detail"/><ErrorState error={detail.error} onRetry={()=>void detail.refetch()}/></div>;
  const job=detail.data.job;
  const controls=<div className="header-actions">{job.status==="submitted"&&<button className="button button-secondary" disabled={accept.isPending} onClick={()=>accept.mutate()}><UserCheck/>Accept job</button>}{["accepted","running"].includes(job.status)&&<button className="button button-primary" disabled={run.isPending} onClick={()=>run.mutate()}><Play/>Run next action</button>}{job.pending_approval_count>0&&<button className="button button-primary" onClick={()=>setApprovalOpen(true)}><CheckCircle2/>Review approval</button>}</div>;
  return <div className="page"><PageHeader eyebrow="Signed execution" title={job.title} detail={`${titleCase(job.status)} · ${titleCase(job.finality)}`} action={controls}/><section className="job-header surface"><div><StatusBadge value={job.status}/><StatusBadge value={job.finality}/></div><dl className="definition-list horizontal"><dt>Job ID</dt><dd><Copyable value={job.job_id} label="job ID"/></dd><dt>Owner</dt><dd className="mono">{shortId(job.owner_fingerprint,16)}</dd><dt>Worker</dt><dd className="mono">{job.worker_fingerprint?shortId(job.worker_fingerprint,16):"Unassigned"}</dd><dt>Created</dt><dd>{formatTimestamp(job.created_at_ms)}</dd></dl></section>
    <div className="job-detail-grid"><section className="surface"><header className="section-heading"><div><h2>Execution Rail</h2><p>Hash-linked job, policy, action, and receipt events.</p></div></header><ExecutionRail events={detail.data.events} selectedId={selected?.event_id ?? null} onSelect={setSelected}/></section><aside className="surface current-gate"><h2>Current gate</h2>{action&&decision?<><StatusBadge value={decision.decision}/><dl className="definition-list"><dt>Tool</dt><dd className="mono">{action.tool_id}</dd><dt>Reason</dt><dd>{decision.reason}</dd><dt>Reason code</dt><dd className="mono">{decision.reason_code}</dd><dt>Readable inputs</dt><dd>{action.input_artifact_ids.length?action.input_artifact_ids.map(id=><Copyable key={id} value={id} label="artifact ID"/>):"None"}</dd><dt>Expected output</dt><dd>{action.expected_output_kind}</dd></dl>{decision.decision==="approval_required"&&<button className="button button-primary button-full" onClick={()=>setApprovalOpen(true)}>Approve or reject</button>}</>:<p className="muted">No action is waiting at a policy or owner gate.</p>}<hr/><h3>Progress</h3><p>{job.completed_action_count} of {job.action_count} actions completed</p></aside></div>
    <Inspector title="Event inspector" open={Boolean(selected)} onClose={()=>setSelected(null)}>{selected&&<><StatusBadge value={selected.event_type}/><dl className="definition-list"><dt>Protocol event</dt><dd><code>{selected.event_type}</code></dd><dt>Sequence</dt><dd>{selected.sequence}</dd><dt>Event hash</dt><dd><Copyable value={selected.event_hash} label="event hash" compact={false}/></dd><dt>Previous hash</dt><dd>{selected.previous_event_hash?<Copyable value={selected.previous_event_hash} label="previous event hash" compact={false}/>:"Genesis event"}</dd><dt>Actor</dt><dd className="mono break-all">{selected.actor_public_key}</dd><dt>Time</dt><dd>{formatTimestamp(selected.created_at_ms)}</dd></dl><h3>Protocol payload</h3><pre>{JSON.stringify(selected.payload as JsonValue,null,2)}</pre></>}</Inspector>
    {action&&decision&&<ApprovalDialog open={approvalOpen} toolId={action.tool_id} argumentsValue={action.arguments} inputIds={action.input_artifact_ids} writeScopes={[]} reason={decision.reason} pending={decide.isPending} onClose={()=>setApprovalOpen(false)} onSubmit={body=>decide.mutate(body,{onSuccess:()=>setApprovalOpen(false)})}/>} {(accept.error||run.error||decide.error)&&<div className="toast-error" role="alert"><XCircle/>{(accept.error??run.error??decide.error)?.message}</div>}
  </div>;
}
