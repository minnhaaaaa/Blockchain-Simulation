import { Dropdown } from "./ui/dropdown";
import { ArrowUp } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { useApi } from "../api/ApiContext";
import { useProviders } from "../api/hooks";
import type { ArtifactRef, Submission } from "../types/api";
import { ArtifactUploader } from "./ArtifactUploader";
import { ErrorState } from "./States";

export function PromptComposer() {
  const { roomId = "" } = useParams(); const { client } = useApi(); const providers = useProviders();
  const navigate = useNavigate(); const queries = useQueryClient();
  const [prompt, setPrompt] = useState(""); const [artifacts, setArtifacts] = useState<ArtifactRef[]>([]);
  const [uploading, setUploading] = useState(false); const [providerId, setProviderId] = useState("");
  const agents = providers.data?.filter(item => item.kind === "openai_compatible") ?? [];
  const active = agents.find(item => item.provider_id === providerId) ?? agents.find(item => item.state === "ready") ?? agents[0];
  const create = useMutation({mutationFn: () => client!.post<Submission>("/api/prompt-jobs", {
    instructions: prompt.trim(), input_artifact_ids: artifacts.map(item => item.artifact_id), provider_id: active?.provider_id
  }), onSuccess: async result => {
    await queries.invalidateQueries({ queryKey: ["jobs"] });
    if (!result.job_id) throw new Error("No job ID returned. Check Jobs before retrying.");
    navigate(`/r/${encodeURIComponent(roomId)}/jobs/${encodeURIComponent(result.job_id)}`, { state: { startAgent: true } });
  }});
  const submit = (event: FormEvent) => { event.preventDefault(); if (prompt.trim() && active?.state === "ready" && !uploading) create.mutate(); };
  return <div className="page prompt-page"><div className="prompt-heading"><h1>What would you like to do?</h1><p>Ask a question or attach a file.</p></div>
    <form className="prompt-form" onSubmit={submit}><label className="sr-only" htmlFor="task-prompt">Your task</label><textarea id="task-prompt" value={prompt} onChange={event => setPrompt(event.target.value)} placeholder="Describe what you need…" rows={4} maxLength={20000} required/>
      <ArtifactUploader compact artifacts={artifacts} onChange={setArtifacts} onBusyChange={setUploading}/>
      <div className="prompt-toolbar"><span>Writes need your approval</span><div>{agents.length > 1 && <Dropdown aria-label="AI provider" value={active?.provider_id ?? ""} onChange={event => setProviderId(event.target.value)}>{agents.map(item => <option key={item.provider_id} value={item.provider_id}>{item.label}</option>)}</Dropdown>}<button className="button button-ink" aria-label="Run task" disabled={!prompt.trim() || active?.state !== "ready" || uploading || create.isPending}>{create.isPending ? "Creating…" : <ArrowUp size={20}/>}</button></div></div>
    </form><p className="prompt-privacy">Your prompt and permitted tool results are sent to your configured AI provider. Files aren’t broadcast to peers. Task instructions and action details are shared with your room.</p>
    {providers.error && <ErrorState error={providers.error}/>}{!providers.isPending && !providers.error && active?.state !== "ready" && <div className="setup-notice"><strong>Connect your agent</strong><p>Add your endpoint, model and API key to <code>agent-provider.local.json</code> on the server. Then refresh.</p><button className="button" onClick={() => void providers.refetch()}>Check connection settings</button></div>}
    {create.error && <ErrorState error={create.error}/>}
  </div>;
}
