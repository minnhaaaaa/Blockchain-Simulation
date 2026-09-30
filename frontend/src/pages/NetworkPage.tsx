import { RefreshCw, Server } from "lucide-react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { usePeers, useStatus } from "../api/hooks";
import { PageHeader } from "../components/AppShell";
import { Copyable } from "../components/Copyable";
import { ErrorState, Skeleton } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { formatTimestamp } from "../utils/format";
import { NetworkOrbit } from "../components/NetworkOrbit";

export function NetworkPage() {
  const { roomId = "" } = useParams(); const peers = usePeers(roomId); const status = useStatus();
  const [selected, setSelected] = useState<string | null>(null);
  const members = (peers.data ?? []).filter(peer => peer.node_id !== status.data?.node_id && (peer.discovery_state === "discovered" || peer.connection_state === "connected"));
  const picked = members.find(peer => peer.node_id === selected);
  // Draw only connections observed by this node, never inferred peer-to-peer edges.
  return <div className="page"><PageHeader title="Network" action={<button className="button" onClick={() => void peers.refetch()}><RefreshCw size={16}/>Refresh</button>}/>
    {peers.error && <ErrorState error={peers.error}/>} {status.error && <ErrorState error={status.error}/>}
    {peers.isPending || status.isPending ? <Skeleton/> : <section className="network-map surface"><div className="section-heading"><span>{members.length + (status.data ? 1 : 0)} participating nodes</span><span className="muted small">Connections seen by {status.data?.node_name ?? "this node"}</span></div>
      <NetworkOrbit members={members} localName={status.data?.node_name} selected={selected} onSelect={setSelected}/><div className="graph-legend"><span>— Connected</span><span>┄ Discovered, not connected</span></div>
      {!members.length && !peers.error && <p className="muted">No peers discovered yet. Join another node to this room to see it here.</p>}
    </section>}
    <div className="node-list">{members.map(peer => <button className={`node-row ${selected === peer.node_id ? "selected" : ""}`} key={peer.node_id} onClick={() => setSelected(selected === peer.node_id ? null : peer.node_id)} aria-expanded={selected === peer.node_id}><Server size={18}/><strong>{peer.name}</strong><StatusBadge value={peer.connection_state}/></button>)}</div>
    {picked && <section className="surface"><h2>{picked.name}</h2><dl className="definition-list"><dt>Discovered</dt><dd>{picked.discovery_state}</dd><dt>Last seen</dt><dd>{formatTimestamp(picked.last_seen_ms)}</dd><dt>Endpoint</dt><dd>{picked.advertised_host}:{picked.advertised_port}</dd><dt>Node ID</dt><dd><Copyable value={picked.node_id} label="node ID"/></dd><dt>Identity</dt><dd><Copyable value={picked.public_key_fingerprint} label="public key fingerprint"/></dd></dl></section>}
  </div>;
}
