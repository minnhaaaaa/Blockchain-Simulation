import { useState } from "react";
import { useApi } from "../api/ApiContext";
import { useProviders, useStatus } from "../api/hooks";
import { PageHeader } from "../components/AppShell";
import { Copyable } from "../components/Copyable";
import { StatusBadge } from "../components/StatusBadge";
import { ErrorState, Skeleton } from "../components/States";

export function SettingsPage() {
  const { apiOrigin, pollIntervalMs, signOut } = useApi(); const status = useStatus(); const providers = useProviders(); const [error, setError] = useState("");
  if (status.isPending) return <div className="page"><Skeleton/></div>;
  if (status.error) return <div className="page"><ErrorState error={status.error}/></div>;
  const leave = async () => { try { await signOut(); } catch { setError("The node could not revoke the session. Local access has been cleared."); } };
  return <div className="page"><PageHeader title="Workspace settings" eyebrow="Your connection" detail="Identity and configuration reported by the running node."/><div className="settings-grid">
    <section className="surface"><h2>Connection</h2><dl className="definition-list"><dt>Node API</dt><dd className="mono break-all">{apiOrigin}</dd><dt>Refresh interval</dt><dd>{pollIntervalMs.toLocaleString()} ms</dd><dt>Frontend version</dt><dd>{__APP_VERSION__}</dd><dt>Room</dt><dd><Copyable value={status.data.room_id} label="room ID"/></dd></dl></section>
    <section className="surface"><h2>Signing identity</h2><dl className="definition-list"><dt>Name</dt><dd>{status.data.node_name}</dd><dt>Node ID</dt><dd><Copyable value={status.data.node_id}/></dd><dt>Fingerprint</dt><dd><Copyable value={status.data.node_public_key_fingerprint} label="fingerprint"/></dd><dt>State</dt><dd><StatusBadge value={status.data.node_state}/></dd></dl></section>
    <section className="surface"><h2>Execution providers</h2>{providers.error ? <ErrorState error={providers.error}/> : providers.isPending ? <Skeleton/> : providers.data?.length ? <ul className="plain-list">{providers.data.map(provider => <li key={provider.provider_id}><span>{provider.label}<small>{provider.kind}</small></span><StatusBadge value={provider.state}/></li>)}</ul> : <p>No providers configured. Add one to the node configuration and restart.</p>}</section>
    <section className="surface"><h2>Operator session</h2><p>Signing out revokes this session at the node and clears it from this browser tab.</p><button className="button button-danger" onClick={() => void leave()}>Sign out</button>{error && <p role="alert">{error}</p>}</section>
  </div></div>;
}
