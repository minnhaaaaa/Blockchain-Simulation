import { Activity, BriefcaseBusiness, Database, Network, Plus, Settings, ShieldCheck, ArrowLeftRight } from "lucide-react";
import { useRef, type PropsWithChildren, type ReactNode } from "react";
import { NavLink, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { useStatus } from "../api/hooks";
import { ConnectionBadge } from "./StatusBadge";
import { Brand } from "./Brand";
import { gsap, useGSAP } from "./Motion";
import { Dock, DockItem, DockIcon, DockLabel } from "./ui/dock";

const navigation = [
  ["overview", "Overview", Activity], ["jobs", "Jobs", BriefcaseBusiness], ["network", "Network", Network],
  ["ledger", "Ledger", Database], ["security", "Security", ShieldCheck], ["settings", "Settings", Settings]
] as const;

export function AppShell({ children }: PropsWithChildren) {
  const { roomId = "" } = useParams(); const status = useStatus(); const location = useLocation();
  const root = useRef<HTMLDivElement>(null);
  useGSAP(() => {
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      const heading = root.current?.querySelector(".page-header");
      if (heading) gsap.from(heading, { autoAlpha: 0, y: 12, duration: 0.4, clearProps: "all" });
    });
    return () => media.revert();
  }, { scope: root, dependencies: [location.pathname], revertOnUpdate: true });
  return <div ref={root} className="app-shell">
    <a href="#main-content" className="skip-link">Skip to workspace</a>
    <Dock>{navigation.map(([slug, label, Icon]) => <DockItem key={slug}><NavLink end={slug === "jobs"} aria-label={label} to={`/r/${encodeURIComponent(roomId)}/${slug}`}><DockIcon><Icon size={21} strokeWidth={1.6}/></DockIcon><DockLabel>{label}</DockLabel></NavLink></DockItem>)}
      <DockItem><NavLink aria-label="Create job" to={`/r/${encodeURIComponent(roomId)}/jobs/new`}><DockIcon><Plus size={23}/></DockIcon><DockLabel>Create job</DockLabel></NavLink></DockItem>
    </Dock>
    <div className="shell-body"><header className="context-bar"><Brand/><div className="context-live"><ConnectionBadge online={Boolean(status.data) && !status.isError}/><span>{status.data?.node_name ?? "Connecting…"}</span></div><NavLink to="/connect?manage" className="icon-button" aria-label="Manage room"><ArrowLeftRight size={18}/></NavLink></header>
      <main id="main-content">{children}</main>
    </div>
  </div>;
}

export function PageHeader({ title, eyebrow, action, detail }: { title: string; eyebrow?: string; detail?: string; action?: ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{detail && <p>{detail}</p>}</div>{action}</header>;
}
export function CreateJobButton() { const { roomId } = useParams(); return <NavLink className="button button-ink" to={`/r/${encodeURIComponent(roomId ?? "")}/jobs/new`}><Plus size={17}/>Create job</NavLink>; }
export function RoomGuard({ children }: PropsWithChildren) {
  const { roomId } = useParams(); const navigate = useNavigate(); const status = useStatus();
  if (status.isPending) return <div className="page"><p role="status">Connecting to your node…</p></div>;
  if (status.isError) return <div className="page"><h1>Node unavailable</h1><p>Start the node, then retry. Your records stay on its disk.</p><button className="button" onClick={() => void status.refetch()}>Retry</button></div>;
  if (status.data.node_state === "starting") return <Navigate to="/connect?manage" replace/>;
  if (status.data.room_id !== roomId) return <div className="page"><h1>Room not active</h1><p>This node is joined to <code>{status.data.room_id}</code>.</p><button className="button button-ink" onClick={() => navigate(`/r/${encodeURIComponent(status.data.room_id)}/overview`)}>Open active room</button></div>;
  return children;
}
