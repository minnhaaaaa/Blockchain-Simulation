import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useParams } from "react-router-dom";
import { CheckCircle2, Download, Play, UserCheck } from "lucide-react";
import { useApi } from "../api/ApiContext";
import { useAcceptJob, useDecideAction, useJob, useJobCommand, useRunJob, useStatus, useProviders } from "../api/hooks";
import { ApprovalDialog } from "../components/ApprovalDialog";
import { ActionComposer } from "../components/ActionComposer";
import { MarkdownAnswer } from "../components/MarkdownAnswer";
import { PageHeader } from "../components/AppShell";
import { Copyable } from "../components/Copyable";
import { ExecutionRail } from "../components/ExecutionRail";
import { Inspector } from "../components/Inspector";
import { ErrorState, Skeleton } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import type { Action, AgentEvent, ArtifactRef, Decision, Job, JobCompleteRequest, Receipt } from "../types/api";
import { eventActionId } from "../utils/events";
import { formatTimestamp, shortId } from "../utils/format";

export function JobDetailPage() {
  const { roomId = "", jobId = "" } = useParams(); const { client } = useApi(); const status = useStatus();
  const detail = useJob(roomId, jobId); const accept = useAcceptJob(roomId, jobId); const run = useRunJob(roomId, jobId);
  const providers = useProviders(); const location = useLocation(); const started = useRef(false);
  const finish = useJobCommand<JobCompleteRequest>(roomId, jobId, "complete");
  const [selected, setSelected] = useState<AgentEvent | null>(null); const [approvalOpen, setApprovalOpen] = useState(false); const [summary, setSummary] = useState(""); const [error, setError] = useState("");
  const events = detail.data?.events ?? [];
  const sourceJob = events.find(event => event.event_type === "job.created")?.payload as unknown as Job | undefined;
  const isAgent = providers.data?.find(provider => provider.provider_id === sourceJob?.provider_id)?.kind === "openai_compatible";
  useEffect(() => {
    if (location.state?.startAgent && isAgent && detail.data?.job.status === "submitted" && !started.current) {
      started.current = true; run.mutate();
    }
  }, [location.state, isAgent, detail.data?.job.status, run]);
  const pending = events.findLast(event => event.event_type === "action.approval_required" && !events.some(later => later.sequence > event.sequence && eventActionId(later) === eventActionId(event) && ["action.approved", "action.rejected"].includes(later.event_type)));
  const pendingId = pending ? eventActionId(pending) : null;
  const action = events.find(event => event.event_type === "action.proposed" && eventActionId(event) === pendingId)?.payload as unknown as Action | undefined;
  const decision = pending?.payload as unknown as Decision | undefined;
  const decide = useDecideAction(roomId, jobId, pendingId ?? "");
  if (detail.isPending) return <div className="page"><PageHeader title="Loading job"/><Skeleton/></div>;
  if (detail.error) return <div className="page"><ErrorState error={detail.error} onRetry={() => void detail.refetch()}/></div>;
  const job = detail.data.job; const source = events.find(event => event.event_type === "job.created")?.payload as unknown as Job;
  const owner = status.data?.node_public_key_fingerprint === job.owner_fingerprint;
  const worker = status.data?.node_public_key_fingerprint === job.worker_fingerprint;
  const executable = worker && ["accepted", "running"].includes(job.status);
  const receipts = events.filter(event => event.event_type === "action.completed").map(event => event.payload as unknown as Receipt);
  const outputs = Array.from(new Map(receipts.flatMap(receipt => receipt.output_artifacts).map(item => [item.artifact_id, item])).values());
  const completedIds = new Set(receipts.map(receipt => receipt.action_id));
  const approvedReady = events.some(event => event.event_type === "action.approved" && !completedIds.has(eventActionId(event) ?? ""));
  const download = async (artifact: ArtifactRef) => {
    setError("");
    try { const blob = await client!.download(`/api/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifact.artifact_id)}`); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = artifact.name; link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Download failed."); }
  };
  const complete = async (e: FormEvent) => { e.preventDefault(); try { await finish.mutateAsync({ summary, output_artifact_ids: outputs.map(item => item.artifact_id) }); } catch { /* displayed below */ } };
  const mutationError = accept.error ?? run.error ?? decide.error ?? finish.error;
  return <div className="page"><PageHeader title={job.title} detail={source.instructions} action={<div className="header-actions">{!isAgent && job.status === "submitted" && <button className="button button-ink" disabled={accept.isPending} onClick={() => accept.mutate()}><UserCheck size={17}/>Accept on this node</button>}{!isAgent && executable && approvedReady && <button className="button button-ink" disabled={run.isPending} onClick={() => run.mutate()}><Play size={17}/>Execute approved action</button>}{owner && pendingId && <button className="button button-ink" onClick={() => setApprovalOpen(true)}>Review approval</button>}</div>}/>
    <section className="job-header"><div className="badge-row"><StatusBadge value={job.status}/><StatusBadge value={job.finality}/></div><dl className="definition-list horizontal"><dt>Job</dt><dd><Copyable value={job.job_id} label="job ID"/></dd><dt>Owner</dt><dd className="mono">{shortId(job.owner_fingerprint)}</dd><dt>Worker</dt><dd className="mono">{job.worker_fingerprint ? shortId(job.worker_fingerprint) : "Awaiting acceptance"}</dd><dt>Created</dt><dd>{formatTimestamp(job.created_at_ms)}</dd></dl></section>
    {(mutationError || error) && <p className="field-error" role="alert">{error || mutationError?.message}</p>}
    <div className="job-detail-grid"><div className="job-workspace">
      {isAgent && (job.status === "submitted" || executable) && !pendingId && <button className="button button-ink" disabled={run.isPending} onClick={() => run.mutate()}><Play size={17}/>{run.isPending ? "Agent is working…" : job.status === "submitted" ? "Run agent" : "Continue agent"}</button>}
      {run.isPending && <p role="status">Waiting for the agent. Tool results will appear below as they are recorded.</p>}
      {events.filter(event => event.event_type === "job.completed").map(event => <section className="surface agent-answer" key={event.event_id}><h2>Result</h2><MarkdownAnswer content={String((event.payload as { summary?: string }).summary ?? "")}/></section>)}
      {!isAgent && executable && !approvedReady && <ActionComposer roomId={roomId} jobId={jobId} inputs={source.input_artifacts}/>}
      <section className="surface"><div className="section-heading"><div><p className="eyebrow">The shared record</p><h2>Execution trail</h2></div><span className="mono muted">{events.length} events</span></div><ExecutionRail events={events} states={detail.data.event_states} selectedId={selected?.event_id ?? null} onSelect={setSelected}/></section>
      {!isAgent && executable && !approvedReady && <section className="surface"><h2>Finish this job</h2><p>Record your conclusion and attach the outputs produced by these actions.</p><form className="form-stack" onSubmit={e => void complete(e)}><label>Completion summary<textarea rows={3} value={summary} onChange={e => setSummary(e.target.value)} required maxLength={4000}/></label><button className="button" disabled={finish.isPending || !summary.trim()}><CheckCircle2 size={17}/>{finish.isPending ? "Recording…" : "Complete job"}</button></form></section>}
    </div><aside className="job-aside"><section className={`surface current-gate ${pendingId ? "gate-waiting" : ""}`}><p className="eyebrow">Current gate</p><h2>{pendingId ? "A decision is needed." : job.status === "completed" ? "Work completed." : "Boundaries in place."}</h2>{action && decision ? <><StatusBadge value={decision.decision}/><p>{decision.reason}</p><dl className="definition-list"><dt>Tool</dt><dd>{action.tool_id}</dd><dt>Writes</dt><dd>{detail.data.action_scopes[action.action_id]?.join(", ") || "None"}</dd></dl>{owner ? <button className="button button-ink button-full" onClick={() => setApprovalOpen(true)}>Review requested action</button> : <p className="muted">The job owner must review this request from their node.</p>}</> : <p>Every proposed action is checked against this job’s signed policy.</p>}<div className="progress-caption"><span>Actions completed</span><strong>{job.completed_action_count} / {job.action_count}</strong></div></section>
      <section className="surface"><h2>Files & outputs</h2>{source.input_artifacts.length + outputs.length === 0 ? <p className="muted">No files for this job yet.</p> : <ul className="download-list">{[...source.input_artifacts, ...outputs].map(item => <li key={item.artifact_id}><div><strong>{item.name}</strong><small>{item.size_bytes.toLocaleString()} bytes</small></div><button className="icon-button" aria-label={`Download ${item.name}`} onClick={() => void download(item)}><Download size={17}/></button></li>)}</ul>}<p className="small muted">Files stay on the node that uploaded or produced them.</p></section>
      <section className="surface"><details><summary>Inspect signed policy</summary><pre>{JSON.stringify(source.policy, null, 2)}</pre></details></section>
    </aside></div>
    <Inspector title="Signed event" open={Boolean(selected)} onClose={() => setSelected(null)}>{selected && <><StatusBadge value={detail.data.event_states[selected.event_id] ?? "pending"}/><h3>{selected.event_type}</h3><dl className="definition-list"><dt>Event hash</dt><dd><Copyable value={selected.event_hash} label="event hash"/></dd><dt>Previous hash</dt><dd>{selected.previous_event_hash ? <Copyable value={selected.previous_event_hash} label="previous hash"/> : "First event"}</dd><dt>Timestamp</dt><dd>{formatTimestamp(selected.created_at_ms)}</dd></dl><pre>{JSON.stringify(selected.payload, null, 2)}</pre></>}</Inspector>
    {action && decision && <ApprovalDialog open={approvalOpen} toolId={action.tool_id} argumentsValue={action.arguments} inputIds={action.input_artifact_ids} writeScopes={detail.data.action_scopes[action.action_id] ?? []} reason={decision.reason} pending={decide.isPending} onClose={() => setApprovalOpen(false)} onSubmit={body => decide.mutate(body, { onSuccess: () => setApprovalOpen(false) })}/>}
  </div>;
}
