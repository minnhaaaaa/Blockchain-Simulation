import { Link2, ShieldX } from "lucide-react";
import type { AgentEvent } from "../types/api";
import { eventRailState } from "../utils/events";
import { formatTimestamp, shortId, titleCase } from "../utils/format";
import { Copyable } from "./Copyable";
import { EmptyState } from "./States";

export function ExecutionRail({ events, selectedId, onSelect, compact = false }: { events: AgentEvent[]; selectedId?: string | null; onSelect?: (event: AgentEvent) => void; compact?: boolean }) {
  if (!events.length) return <EmptyState title="No execution events" detail="Signed job and action events will appear here after submission." />;
  return <ol className={`execution-rail ${compact ? "rail-compact" : ""}`} aria-label="Execution event chain">
    {events.map((event, index) => {
      const broken = index > 0 && event.previous_event_hash !== events[index - 1]?.event_hash;
      return <li key={event.event_id} className={`execution-node rail-${eventRailState(event)} ${selectedId === event.event_id ? "is-selected" : ""}`}>
        <button type="button" onClick={() => onSelect?.(event)} aria-current={selectedId === event.event_id ? "step" : undefined}>
          <span className="rail-marker">{broken ? <ShieldX size={16} /> : <Link2 size={16} />}</span>
          <span className="rail-content"><span className="rail-title">{titleCase(event.event_type)}</span><code>{event.event_type}</code>
          {!compact && <><span className="rail-meta">Sequence {event.sequence} · {formatTimestamp(event.created_at_ms)}</span><span className="rail-meta">Actor {shortId(event.actor_public_key, 16)}</span><Copyable value={event.event_hash} label="event hash" /></>}</span>
        </button>
        {broken && <p className="rail-warning">Hash link does not match the previous displayed event.</p>}
      </li>;
    })}
  </ol>;
}
