import { ArrowUpRight, Network, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { useChain, useJobs, usePeers, useStatus, useViolations } from "../api/hooks";
import { CreateJobButton, PageHeader } from "../components/AppShell";
import { EmptyState, ErrorState, Skeleton, StaleDataBanner } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { formatTimestamp, shortId } from "../utils/format";

export function OverviewPage() {
  const { roomId = "" } = useParams(); const status = useStatus(); const jobs = useJobs(roomId); const peers = usePeers(roomId); const chain = useChain(roomId, 6); const violations = useViolations(roomId);
  const queries = [status, jobs, peers, chain, violations]; const errors = queries.filter(query => query.error);
  const pending = jobs.data?.reduce((sum, job) => sum + job.pending_approval_count, 0);
  const active = jobs.data?.filter(job => !["completed", "failed", "expired"].includes(job.status)).length;
  const root = `/r/${encodeURIComponent(roomId)}`;
  return <div className="page overview-page"><PageHeader title="Your work, in view." action={<CreateJobButton/>}/>
    {queries.some(query => query.isRefetchError) && <StaleDataBanner onRetry={() => void Promise.all(queries.map(query => query.refetch()))}/>}
    {errors.map((query, index) => <ErrorState key={index} error={query.error} onRetry={() => void query.refetch()}/>)}
    <section className="overview-metrics" aria-label="Live workspace metrics"><Metric label="Active jobs" value={active}/><Metric label="Awaiting your approval" value={pending}/><Metric label="Finalized height" value={chain.data?.finalized_height}/><Metric label="Security events" value={violations.data?.length}/></section>
    <div className="overview-grid"><section className="work-panel"><header className="section-heading"><div><p className="eyebrow">On your desk</p><h2>Recent work</h2></div><Link className="text-link" to={`${root}/jobs`}>All jobs <ArrowUpRight size={17}/></Link></header>
      {jobs.isPending ? <Skeleton rows={6}/> : jobs.data?.length ? <div className="work-list">{[...jobs.data].sort((a, b) => b.updated_at_ms - a.updated_at_ms).slice(0, 6).map(job => <Link key={job.job_id} to={`${root}/jobs/${job.job_id}`} className="work-row"><span className="work-icon"><ShieldCheck strokeWidth={1.4}/></span><div><h3>{job.title}</h3><span>{job.completed_action_count} / {job.action_count} actions · {formatTimestamp(job.updated_at_ms)}</span></div><div className="work-badges"><StatusBadge value={job.status}/><StatusBadge value={job.finality}/></div><ArrowUpRight size={18}/></Link>)}</div> : !jobs.error && <EmptyState title="Room to begin." detail="Create your first job with your own inputs and permissions. Its real execution record will appear here." action={<CreateJobButton/>}/>}
    </section><aside className="network-card"><div className="section-heading"><span className="eyebrow">Your network</span><Network size={22}/></div><h2>Independent nodes.<br/>One shared record.</h2><div className="network-count"><strong>{peers.data ? peers.data.filter(peer => peer.connection_state === "connected").length : "—"}</strong><span>connected peers</span></div><div className="network-detail"><span>Local node</span><strong>{status.data?.node_name ?? "Connecting…"}</strong></div><div className="network-detail"><span>Chain height</span><strong>{chain.data?.height ?? "—"}</strong></div><div className="network-detail"><span>Head hash</span><strong className="mono">{chain.data ? shortId(chain.data.head_hash, 16) : "—"}</strong></div><Link to={`${root}/network`} className="button button-lime button-full">Inspect network <ArrowUpRight size={17}/></Link></aside></div>
    <section className="surface latest-blocks"><header className="section-heading"><div><p className="eyebrow">Written to the ledger</p><h2>Recent blocks</h2></div><Link className="text-link" to={`${root}/ledger`}>Open ledger <ArrowUpRight size={17}/></Link></header>{chain.isPending ? <Skeleton/> : chain.data?.blocks.some(block => block.height > 0) ? <div className="block-strip">{chain.data.blocks.filter(block => block.height > 0).map(block => <Link to={`${root}/ledger`} key={block.block_id}><span className="mono block-height">#{block.height}</span><StatusBadge value={block.finality}/><strong>{block.transaction_count} entries</strong><small className="mono">{shortId(block.hash, 18)}</small></Link>)}</div> : !chain.error && <EmptyState title="No task activity yet" detail="Your network has a genesis block—the starting record. Task activity will appear after you run work."/>}</section>
  </div>;
}
function Metric({ label, value }: { label: string; value: number | undefined }) { return <div><span>{label}</span><strong>{value === undefined ? "—" : value.toLocaleString()}</strong></div>; }
