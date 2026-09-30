import { Link2, ShieldX } from "lucide-react";
import type { AgentEvent } from "../types/api";
import { eventRailState } from "../utils/events";
import { formatTimestamp, shortId, titleCase } from "../utils/format";
import { Copyable } from "./Copyable";
import { EmptyState } from "./States";
import { StatusBadge } from "./StatusBadge";

export function ExecutionRail({ events, states = {}, selectedId, onSelect, compact = false }: { events: AgentEvent[]; states?: Record<string,string>; selectedId?: string | null; onSelect?: (event: AgentEvent) => void; compact?: boolean }) {
  if (!events.length) return <EmptyState title="No execution events" detail="Signed job and action events will appear here after submission." />;
  return <ol className={`execution-rail ${compact ? "rail-compact" : ""}`} aria-label="Execution event chain">
    {events.map((event, index) => {
      const broken = index > 0 && event.previous_event_hash !== events[index - 1]?.event_hash;
      return <li key={event.event_id} className={`execution-node rail-${eventRailState(event)} ${selectedId === event.event_id ? "is-selected" : ""}`}>
        <button type="button" onClick={() => onSelect?.(event)} aria-current={selectedId === event.event_id ? "step" : undefined}>
          <span className="rail-marker">{broken ? <ShieldX size={16} /> : <Link2 size={16} />}</span>
          <span className="rail-content"><span className="rail-title">{titleCase(event.event_type)}</span><code>{event.event_type}</code>
          {!compact && <><span className="rail-meta">Sequence {event.sequence} · {formatTimestamp(event.created_at_ms)}</span><span className="rail-meta">{shortId(event.event_hash, 18)}</span></>}</span>
        </button>
        {states[event.event_id] && <StatusBadge value={states[event.event_id] ?? "pending"}/>}
        {!compact && <Copyable value={event.event_hash} label="event hash"/>}
        {broken && <p className="rail-warning">Hash link does not match the previous displayed event.</p>}
      </li>;
    })}
  </ol>;
}
