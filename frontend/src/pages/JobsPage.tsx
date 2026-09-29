import { Search } from "lucide-react";
import { useMemo } from "react";
import { Link, useSearchParams, useParams } from "react-router-dom";
import { useJobs } from "../api/hooks";
import { CreateJobButton, PageHeader } from "../components/AppShell";
import { Copyable } from "../components/Copyable";
import { EmptyState, ErrorState, Skeleton } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import type { JobStatus } from "../types/api";
import { formatTimestamp, shortId, titleCase } from "../utils/format";

const structuralStates: JobStatus[] = ["draft","submitted","accepted","running","waiting_approval","completed","failed","expired"];

export function JobsPage() {
  const roomId = useParams().roomId ?? ""; const [params,setParams] = useSearchParams(); const status = params.get("state") ?? ""; const query = params.get("q") ?? ""; const jobs = useJobs(roomId, status || undefined);
  const filtered = useMemo(() => (jobs.data ?? []).filter(job => !query || `${job.title} ${job.owner_fingerprint} ${job.worker_fingerprint ?? ""}`.toLowerCase().includes(query.toLowerCase())), [jobs.data,query]);
  const update = (key:string,value:string) => { const next=new URLSearchParams(params); if(value) next.set(key,value); else next.delete(key); setParams(next,{replace:true}); };
  return <div className="page"><PageHeader eyebrow="Execution inventory" title="Jobs" detail="Search live projections without duplicating server state." action={<CreateJobButton />} /><div className="filter-bar"><label><Search />Search jobs<input value={query} onChange={event => update("q",event.target.value)} /></label><label>Job state<select value={status} onChange={event => update("state",event.target.value)}><option value="">All states</option>{structuralStates.map(value => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label></div>
    <section className="surface">{jobs.isPending ? <Skeleton rows={7} /> : jobs.error ? <ErrorState error={jobs.error} onRetry={() => void jobs.refetch()} /> : !filtered.length ? <EmptyState title={jobs.data?.length ? "No jobs match these filters" : "No jobs have been submitted in this room."} detail={jobs.data?.length ? "Clear or change the filters to inspect other jobs." : "Create a job to begin."} action={!jobs.data?.length ? <CreateJobButton /> : undefined} /> : <div className="table-wrap"><table><thead><tr><th>Job</th><th>State</th><th>Owner / worker</th><th>Actions</th><th>Ledger</th><th>Updated</th></tr></thead><tbody>{filtered.map(job => <tr key={job.job_id}><td><Link to={`/r/${roomId}/jobs/${job.job_id}`}><strong>{job.title}</strong></Link><Copyable value={job.job_id} label="job ID" /></td><td><StatusBadge value={job.status} /></td><td><span className="mono">{shortId(job.owner_fingerprint)}</span><small>{job.worker_fingerprint ? ` / ${shortId(job.worker_fingerprint)}` : " / unassigned"}</small></td><td>{job.completed_action_count}/{job.action_count}{job.pending_approval_count ? <small className="attention-text"> · {job.pending_approval_count} waiting</small> : null}</td><td><StatusBadge value={job.finality} /></td><td>{formatTimestamp(job.updated_at_ms)}</td></tr>)}</tbody></table></div>}</section></div>;
}
