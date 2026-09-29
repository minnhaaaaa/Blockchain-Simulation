import { Activity, BriefcaseBusiness, ChevronLeft, Database, Menu, Network, Plus, Settings, ShieldCheck, X } from "lucide-react";
import { useState, type PropsWithChildren, type ReactNode } from "react";
import { NavLink, Navigate, useLocation, useNavigate, useParams } from "react-router-dom";
import { useApi } from "../api/ApiContext";
import { useStatus } from "../api/hooks";
import { relativeAge, shortId } from "../utils/format";
import { ConnectionBadge, StatusBadge } from "./StatusBadge";

const navItems = [
  ["overview", "Overview", Activity], ["jobs", "Jobs", BriefcaseBusiness], ["network", "Network", Network],
  ["ledger", "Ledger", Database], ["security", "Security", ShieldCheck], ["settings", "Settings", Settings]
] as const;

export function AppShell({ children }: PropsWithChildren) {
  const { roomId } = useParams(); const { client } = useApi(); const [mobileOpen, setMobileOpen] = useState(false); const status = useStatus(Boolean(client));
  if (!client) return <Navigate to="/" replace />;
  const activeRoom = roomId ?? status.data?.room_id;
  return <div className="app-shell">
    <button className="mobile-menu button button-secondary" onClick={() => setMobileOpen(true)}><Menu size={18} />Menu</button>
    <aside className={`side-rail ${mobileOpen ? "is-open" : ""}`} aria-label="Primary navigation">
      <div className="brand"><span className="brand-mark">AG</span><span><strong>AgentGuard</strong><small>Execution console</small></span><button className="mobile-close icon-button" aria-label="Close navigation" onClick={() => setMobileOpen(false)}><X /></button></div>
      <div className="room-chip"><small>Current room</small><strong>{activeRoom ? shortId(activeRoom, 18) : "Not joined"}</strong></div>
      <nav>{activeRoom && navItems.map(([slug, label, Icon]) => <NavLink key={slug} to={`/r/${encodeURIComponent(activeRoom)}/${slug}`} onClick={() => setMobileOpen(false)}><Icon size={17} />{label}</NavLink>)}</nav>
      <NavLink className="switch-room" to="/"><ChevronLeft size={16} />Switch room</NavLink>
    </aside>
    <div className="shell-body">
      <header className="context-bar">
        <ConnectionBadge online={!status.isError} />
        <span className="context-item"><small>Node</small><strong>{status.data?.node_name ?? "Loading…"}</strong></span>
        <span className="context-item context-provider"><small>Provider</small>{status.data && <StatusBadge value={status.data.provider_state} />}</span>
        <span className="context-item context-height"><small>Finalized height</small><strong>{status.data?.finalized_height ?? "—"}</strong></span>
        <span className="context-updated">Updated {relativeAge(status.dataUpdatedAt)}</span>
      </header>
      <main id="main-content">{children}</main>
    </div>
  </div>;
}

export function PageHeader({ title, eyebrow, action, detail }: { title: string; eyebrow?: string; detail?: string; action?: ReactNode }) {
  return <header className="page-header"><div>{eyebrow && <p className="eyebrow">{eyebrow}</p>}<h1>{title}</h1>{detail && <p>{detail}</p>}</div>{action}</header>;
}

export function CreateJobButton() { const { roomId } = useParams(); return <NavLink className="button button-primary" to={`/r/${encodeURIComponent(roomId ?? "")}/jobs/new`}><Plus size={17} />Create job</NavLink>; }

export function RoomGuard({ children }: PropsWithChildren) {
  const { roomId } = useParams(); const location = useLocation(); const navigate = useNavigate(); const status = useStatus();
  if (status.isPending) return <div className="page"><p role="status">Connecting to the configured node…</p></div>;
  if (status.isError) return <div className="page"><h1>Node unavailable</h1><p>The configured application API could not provide room status.</p><button className="button" onClick={() => void status.refetch()}>Retry</button></div>;
  if (!status.data.room_id) return <Navigate to="/" state={{ from: location.pathname }} replace />;
  if (status.data.room_id !== roomId) return <div className="page"><h1>Room not active</h1><p>This node is joined to <code>{status.data.room_id}</code>, not the requested room.</p><button className="button button-primary" onClick={() => navigate(`/r/${encodeURIComponent(status.data.room_id)}/overview`)}>Open active room</button></div>;
  return children;
}
