import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, Plus } from "lucide-react";
import { useApi } from "../api/ApiContext";
import { useConfigureRoom } from "../api/hooks";
import { Brand } from "../components/Brand";
import { Copyable } from "../components/Copyable";
import { ErrorState } from "../components/States";
import { Reveal } from "../components/Motion";
import type { ConsensusParameters, GenesisAllocation, RoomManifest, RoomSessionRequest } from "../types/api";
import manifestSchema from "../../../contracts/schemas/room-manifest.schema.json";

export function GatewayPage() {
  const { client, apiOrigin, signOut } = useApi(); const navigate = useNavigate(); const [params] = useSearchParams(); const qc = useQueryClient();
  const current = useQuery({ queryKey: ["room-session", apiOrigin], queryFn: () => client!.get<{ manifest: RoomManifest | null }>("/api/room-session") });
  const identity = useQuery({ queryKey: ["identity", apiOrigin], queryFn: () => client!.get<{ public_key: string; node_name: string }>("/api/identity") });
  const configure = useConfigureRoom(); const [mode, setMode] = useState<"join" | "create">("join");
  const [roomId, setRoomId] = useState(""); const [protocol, setProtocol] = useState(""); const [error, setError] = useState("");
  const [consensus, setConsensus] = useState<Record<string, string>>({});
  const [allocations, setAllocations] = useState<Array<{ public_key: string; amount: string; stake: string }>>([]);
  useEffect(() => { if (current.data?.manifest && !params.has("manage")) navigate(`/r/${encodeURIComponent(current.data.manifest.room_id)}/overview`, { replace: true }); }, [current.data, navigate, params]);
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setError("");
    try {
      const body: RoomSessionRequest = mode === "join" ? { operation: "join", room_id: roomId.trim() } : {
        operation: "create", room_id: roomId.trim(), protocol_version: protocol,
        consensus_parameters: Object.fromEntries(Object.entries(consensus).map(([key, value]) => [key, Number(value)])) as ConsensusParameters,
        genesis_allocations: allocations.map(item => ({ public_key: item.public_key, amount: Number(item.amount), stake: Number(item.stake) })) as GenesisAllocation[]
      };
      const result = await configure.mutateAsync(body); await qc.invalidateQueries(); navigate(`/r/${encodeURIComponent(result.room_id)}/overview`);
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not configure the room."); }
  };
  return <main className="connect-page"><header><Brand/><button className="text-link" onClick={() => void signOut()}>Sign out / switch node</button></header><Reveal className="connect-content"><p className="eyebrow">Connected to {identity.data?.node_name ?? apiOrigin}</p><h1>A room for your network.</h1><p>Join peers with a room ID, or define a new network and its validator allocations.</p>
    {current.error && <ErrorState error={current.error} onRetry={() => void current.refetch()}/>}
    {current.data?.manifest && <section className="active-room"><div><span className="eyebrow">Active room</span><Copyable value={current.data.manifest.room_id} label="room ID" compact={false}/></div><button className="button button-ink" onClick={() => navigate(`/r/${encodeURIComponent(current.data!.manifest!.room_id)}/overview`)}>Open workspace <ArrowRight size={16}/></button></section>}
    <div className="tabs" role="tablist" aria-label="Room operation"><button role="tab" aria-selected={mode === "join"} onClick={() => setMode("join")}>Join a room</button><button role="tab" aria-selected={mode === "create"} onClick={() => setMode("create")}>Create a room</button></div>
    <form className="form-stack" onSubmit={e => void submit(e)}><label>Room ID<div className="input-action"><input value={roomId} onChange={e => setRoomId(e.target.value)} minLength={3} maxLength={128} required/>{mode === "create" && <button type="button" className="button" onClick={() => setRoomId(`room-${crypto.randomUUID()}`)}>Generate</button>}</div></label>
      {mode === "create" && <><label>Protocol version<input value={protocol} onChange={e => setProtocol(e.target.value)} required/></label><fieldset><legend>Consensus settings</legend><p className="muted">These settings become part of the signed room manifest.</p><div className="form-grid">{Object.entries(manifestSchema.$defs.consensusParameters.properties).map(([key, schema]) => <label key={key}>{key.replaceAll("_", " ")}<input type="number" step="1" min={schema.minimum} value={consensus[key] ?? ""} onChange={e => setConsensus(value => ({ ...value, [key]: e.target.value }))} required/></label>)}</div></fieldset>
      <fieldset><legend>Genesis allocations</legend>{allocations.map((item, index) => <div className="allocation-row" key={index}><label>Public key<textarea value={item.public_key} onChange={e => setAllocations(items => items.map((v, i) => i === index ? { ...v, public_key: e.target.value } : v))} required/></label><label>Balance<input type="number" min="1" value={item.amount} onChange={e => setAllocations(items => items.map((v, i) => i === index ? { ...v, amount: e.target.value } : v))} required/></label><label>Validator stake<input type="number" min="0" value={item.stake} onChange={e => setAllocations(items => items.map((v, i) => i === index ? { ...v, stake: e.target.value } : v))} required/></label><button type="button" className="text-link" onClick={() => setAllocations(items => items.filter((_, i) => i !== index))}>Remove</button></div>)}<div className="button-row"><button type="button" className="button" disabled={!identity.data} onClick={() => setAllocations(items => [...items, { public_key: identity.data!.public_key, amount: "", stake: "" }])}><Plus size={16}/>This node</button><button type="button" className="button" onClick={() => setAllocations(items => [...items, { public_key: "", amount: "", stake: "" }])}>Another node</button></div></fieldset></>}
      {error && <p role="alert" className="field-error">{error}</p>}<button className="button button-ink" disabled={configure.isPending || (mode === "create" && !allocations.length)}>{configure.isPending ? "Applying signed manifest…" : mode === "join" ? "Join room" : "Sign and create room"}<ArrowRight size={17}/></button>
    </form>{identity.data && <details className="identity-disclosure"><summary>This node’s public key</summary><Copyable value={identity.data.public_key} label="public key" compact={false}/></details>}</Reveal></main>;
}
