import { Dropdown } from "../components/ui/dropdown";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { ArrowRight, KeyRound, ShieldCheck } from "lucide-react";
import { ApiClient, normalizeApiOrigin } from "../api/client";
import { useApi } from "../api/ApiContext";
import type { OperatorSession } from "../types/api";
import { Brand } from "../components/Brand";
import { Reveal } from "../components/Motion";

export function SignInPage() {
  const { client, signIn } = useApi(); const navigate = useNavigate();
  const configuration = window.__AGENTGUARD_CONFIG__;
  const [origin, setOrigin] = useState(configuration?.apiOrigin ?? "");
  const [key, setKey] = useState(""); const [poll, setPoll] = useState(String(configuration?.pollIntervalMs ?? ""));
  const [error, setError] = useState(""); const [pending, setPending] = useState(false);
  if (client) return <Navigate to="/connect" replace/>;
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setPending(true); setError("");
    try {
      const apiOrigin = normalizeApiOrigin(origin); const interval = Number(poll);
      if (!Number.isSafeInteger(interval) || interval < 1000) throw new Error("Live refresh must be at least 1000 milliseconds.");
      const result = await new ApiClient(apiOrigin).post<OperatorSession>("/api/auth/login", { access_key: key });
      signIn({ origin: apiOrigin, token: result.token, expiresAt: result.expires_at_ms, pollIntervalMs: interval });
      setKey(""); navigate("/connect", { replace: true });
    } catch (cause) { setError(cause instanceof Error ? cause.message : "Could not sign in."); }
    finally { setPending(false); }
  };
  return <main className="auth-page"><div className="auth-story"><Brand/><div><p className="eyebrow">Your node. Your workspace.</p><h1>Good work starts<br/>with <em>permission.</em></h1><p>Sign in as this node’s operator to create work, review actions, and follow the evidence.</p></div><span className="auth-foot"><ShieldCheck size={18}/>Signing keys stay inside the node.</span></div>
    <Reveal className="auth-panel"><Link to="/" className="text-link">← Back to Certa</Link><div className="auth-form-heading"><KeyRound/><p className="eyebrow">Operator access</p><h2>Welcome to your workspace.</h2><p>Use the access key generated when you started your node.</p></div>
      <form onSubmit={event => void submit(event)} className="form-stack">
        {Boolean(configuration?.nodes?.length) && <label>Running node<Dropdown aria-label="Running node" value={origin} onChange={e => setOrigin(e.target.value)}><option value="">Choose a running node</option>{configuration?.nodes?.map(node => <option key={node.apiOrigin} value={node.apiOrigin}>{node.name}</option>)}</Dropdown></label>}
        <label>Node API URL<input type="url" autoComplete="url" value={origin} onChange={e => setOrigin(e.target.value)} required/></label>
        <label>Node access key<input type="password" autoComplete="current-password" value={key} onChange={e => setKey(e.target.value)} required/><span>Find it in this run’s private operator-access.json file.</span></label>
        {!configuration?.pollIntervalMs && <label>Live refresh interval (ms)<input type="number" min="1000" step="1" value={poll} onChange={e => setPoll(e.target.value)} required/></label>}
        {error && <p className="field-error" role="alert">{error}</p>}
        <button className="button button-ink button-full" disabled={pending}>{pending ? "Signing in…" : "Sign in"}<ArrowRight size={18}/></button>
      </form><p className="auth-note">Sessions are verified by your node and expire automatically. No shared account or preset credentials.</p>
    </Reveal></main>;
}
