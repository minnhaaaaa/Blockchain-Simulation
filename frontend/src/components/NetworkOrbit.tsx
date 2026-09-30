import { useEffect, useRef, useState } from "react";
import { Pause, Play, RotateCcw, ZoomIn, ZoomOut } from "lucide-react";
import { useReducedMotion } from "./ui/use-reduced-motion";
import type { Peer } from "../types/api";

export function NetworkOrbit({ members, localName, selected, onSelect }: { members: Peer[]; localName: string | undefined; selected: string | null; onSelect: (id: string) => void }) {
  const svg = useRef<SVGSVGElement>(null); const phase = useRef(0); const pointer = useRef({ x: 0, y: 0 });
  const [paused, setPaused] = useState(false); const [zoom, setZoom] = useState(1); const reduced = useReducedMotion();
  const membership = members.map(peer => peer.node_id).join(",");
  useEffect(() => {
    const root = svg.current!; const nodes = [...root.querySelectorAll<SVGGElement>(".orbit-node")];
    const edges = [...root.querySelectorAll<SVGLineElement>(".orbit-edge")];
    let frame = 0, previous = 0; let offsetX = 0, offsetY = 0;
    const draw = (time: number) => {
      if (!document.hidden && !paused && !reduced && !root.matches(":hover, :focus-within")) {
        phase.current += previous ? Math.min(time - previous, 50) * 0.00012 : 0;
      }
      previous = time;
      if (!paused && !reduced) { offsetX += (pointer.current.x - offsetX) * 0.06; offsetY += (pointer.current.y - offsetY) * 0.06; }
      nodes.forEach((node, index) => {
        const angle = phase.current + index / nodes.length * Math.PI * 2 - Math.PI / 2;
        const x = 400 + 245 * Math.cos(angle) + offsetX, y = 260 + 153 * Math.sin(angle) + offsetY;
        node.setAttribute("transform", `translate(${x} ${y})`);
        edges[index]?.setAttribute("x2", String(x)); edges[index]?.setAttribute("y2", String(y));
      });
      if (!reduced && !paused && !document.hidden) frame = requestAnimationFrame(draw);
    };
    const start = () => { cancelAnimationFrame(frame); previous = 0; draw(performance.now()); };
    start(); document.addEventListener("visibilitychange", start);
    return () => { cancelAnimationFrame(frame); document.removeEventListener("visibilitychange", start); };
  }, [membership, paused, reduced]);
  return <div className="orbit-stage"><div className="graph-controls"><span>Hover to hold · select a node</span>
    <button className="icon-button" aria-label={paused ? "Resume orbit" : "Pause orbit"} aria-pressed={paused} disabled={Boolean(reduced)} onClick={() => setPaused(value => !value)}>{paused ? <Play size={16}/> : <Pause size={16}/>}</button>
    <button className="icon-button" aria-label="Zoom out" disabled={zoom <= 0.7} onClick={() => setZoom(value => Math.max(0.7, value - 0.1))}><ZoomOut size={16}/></button>
    <button className="icon-button" aria-label="Zoom in" disabled={zoom >= 1.4} onClick={() => setZoom(value => Math.min(1.4, value + 0.1))}><ZoomIn size={16}/></button>
    <button className="icon-button" aria-label="Reset zoom" onClick={() => setZoom(1)}><RotateCcw size={16}/></button>
  </div><svg ref={svg} className="peer-graph" viewBox="0 0 800 520" role="group" aria-label="Live room connections"
    onPointerMove={event => { if (event.pointerType !== "mouse") return; const bounds = event.currentTarget.getBoundingClientRect(); pointer.current = { x: ((event.clientX - bounds.left) / bounds.width - 0.5) * 35, y: ((event.clientY - bounds.top) / bounds.height - 0.5) * 30 }; }} onPointerLeave={() => { pointer.current = { x: 0, y: 0 }; }}>
    <g transform={`translate(400 260) scale(${zoom}) translate(-400 -260)`}>
      <ellipse className="orbit-track" cx="400" cy="260" rx="245" ry="153"/>
      {localName && members.map(peer => <line key={peer.node_id} className={`orbit-edge ${peer.connection_state === "connected" ? "graph-connected" : "graph-discovered"}`} x1="400" y1="260" x2="400" y2="260"/>)}
      {localName && <g><circle cx="400" cy="260" r="43" className="graph-local"/><text x="400" y="265" className="graph-symbol">Certa</text><text x="400" y="327">{localName}</text><text x="400" y="348" className="graph-caption">This node</text></g>}
      {members.map(peer => <g key={peer.node_id} className="graph-peer orbit-node" role="button" tabIndex={0} aria-label={`Inspect ${peer.name}`} aria-pressed={selected === peer.node_id}
        onClick={() => onSelect(peer.node_id)} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(peer.node_id); } }}>
        <circle r="25" className={selected === peer.node_id ? "graph-selected" : ""}/><text y="5" className="graph-symbol">{peer.name.slice(0, 1).toUpperCase()}</text><text y="46">{peer.name.length > 24 ? `${peer.name.slice(0, 21)}…` : peer.name}</text><text y="65" className="graph-caption">{peer.connection_state}</text>
      </g>)}
    </g></svg></div>;
}
