import { Dropdown } from "../components/ui/dropdown";
import { Braces, Plus, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useCreateJob, useProviders, useTools } from "../api/hooks";
import { PageHeader } from "../components/AppShell";
import { ArtifactUploader } from "../components/ArtifactUploader";
import { ErrorState, Skeleton } from "../components/States";
import type { ArtifactRef, PolicyRuleInput } from "../types/api";
import { serializePolicyDraft, type RuleDraft } from "../utils/policy";
import { PromptComposer } from "../components/PromptComposer";

const blankRule = (): RuleDraft => ({ tool_id: "", effect: "allow", read_artifact_ids: [], write_scopes: "", argument_constraints: "{}" });

export function NewJobPage() {
  const [advanced, setAdvanced] = useState(false);
  return <><div className="creation-mode"><button className="text-link" onClick={() => setAdvanced(value => !value)}>{advanced ? "Back to prompt" : "Advanced setup"}</button></div>{advanced ? <AdvancedJobPage/> : <PromptComposer/>}</>;
}

function AdvancedJobPage() {
  const roomId = useParams().roomId ?? ""; const navigate = useNavigate(); const providers = useProviders(); const tools = useTools(); const create = useCreateJob(roomId);
  const [title, setTitle] = useState(""); const [instructions, setInstructions] = useState(""); const [providerId, setProviderId] = useState("");
  const [artifacts, setArtifacts] = useState<ArtifactRef[]>([]); const [uploading, setUploading] = useState(false); const [rules, setRules] = useState<RuleDraft[]>([blankRule()]);
  const [maxActions, setMaxActions] = useState(""); const [maxRuntime, setMaxRuntime] = useState(""); const [maxOutput, setMaxOutput] = useState(""); const [expiry, setExpiry] = useState("");
  const [rawMode, setRawMode] = useState(false); const [rawPolicy, setRawPolicy] = useState(""); const [formError, setFormError] = useState("");
  const draft = useMemo(() => ({ rules, maxActions, maxRuntime, maxOutput, expiry, rawMode, rawPolicy }), [rules, maxActions, maxRuntime, maxOutput, expiry, rawMode, rawPolicy]);
  const validation = useMemo(() => {
    const errors: string[] = [];
    if (!title.trim() || !instructions.trim()) errors.push("Add a title and instructions.");
    if (!providerId) errors.push("Choose an execution provider.");
    if (uploading) errors.push("Wait for your files to finish uploading.");
    if (!rawMode && (!rules.length || rules.some(rule => !rule.tool_id))) errors.push("Choose a tool for each permission rule.");
    try { serializePolicyDraft(draft); } catch (cause) { errors.push(cause instanceof Error ? cause.message : "Complete the policy."); }
    return errors;
  }, [title, instructions, providerId, uploading, rawMode, rules, draft]);
  const updateRule = (index: number, patch: Partial<RuleDraft>) => setRules(items => items.map((item, i) => i === index ? { ...item, ...patch } : item));
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setFormError(""); if (validation.length) return;
    try {
      const result = await create.mutateAsync({ title: title.trim(), instructions: instructions.trim(), provider_id: providerId, input_artifact_ids: artifacts.map(item => item.artifact_id), policy: serializePolicyDraft(draft) });
      if (!result.job_id) throw new Error("The server did not return the new job ID. Check Jobs before retrying.");
      navigate(`/r/${encodeURIComponent(roomId)}/jobs/${encodeURIComponent(result.job_id)}`);
    } catch (cause) { setFormError(cause instanceof Error ? cause.message : "Could not create the job."); }
  };
  if (providers.isPending || tools.isPending) return <div className="page"><PageHeader title="Create a job"/><Skeleton/></div>;
  if (providers.error || tools.error) return <div className="page"><ErrorState error={providers.error ?? tools.error}/></div>;
  return <div className="page"><PageHeader eyebrow="Make the boundaries clear" title="Create a job" detail="Describe the work. Bring your files. Decide what can happen."/>
    <form className="composer-layout" onSubmit={e => void submit(e)}><div className="composer-main">
      <section className="surface form-section"><span className="step-number">1</span><div><h2>The work</h2><label>Title<input value={title} onChange={e => setTitle(e.target.value)} maxLength={160} required/></label><label>Instructions<textarea rows={4} value={instructions} onChange={e => setInstructions(e.target.value)} maxLength={20000} required/></label><label>Execution provider<Dropdown value={providerId} onChange={e => setProviderId(e.target.value)} required><option value="">Choose a configured provider</option>{providers.data?.map(provider => <option key={provider.provider_id} value={provider.provider_id} disabled={provider.state !== "ready"}>{provider.label} · {provider.kind}</option>)}</Dropdown><span>Manual providers execute the actions you propose from the job page.</span></label></div></section>
      <section className="surface form-section"><span className="step-number">2</span><div><h2>Your inputs</h2><ArtifactUploader artifacts={artifacts} onBusyChange={setUploading} onChange={items => { setArtifacts(items); const retained = new Set(items.map(item => item.artifact_id)); setRules(current => current.map(rule => ({ ...rule, read_artifact_ids: rule.read_artifact_ids.filter(id => retained.has(id)) }))); }}/></div></section>
      <section className="surface form-section"><span className="step-number">3</span><div><div className="section-heading"><div><h2>The boundaries</h2><p>Anything without a matching permission is denied.</p></div><button type="button" className="button" onClick={() => { if (!rawMode) { try { setRawPolicy(JSON.stringify(serializePolicyDraft(draft), null, 2)); } catch { /* start with operator input */ } } setRawMode(value => !value); }}><Braces size={16}/>{rawMode ? "Rule builder" : "Edit JSON"}</button></div>
        {rawMode ? <label>Policy JSON<textarea className="code-editor" rows={16} value={rawPolicy} onChange={e => setRawPolicy(e.target.value)}/></label> : <>{rules.map((rule, index) => <fieldset key={index} className="policy-rule"><legend>Permission {index + 1}</legend><button type="button" className="icon-button rule-remove" aria-label={`Remove rule ${index + 1}`} onClick={() => setRules(items => items.filter((_, i) => i !== index))}><Trash2 size={16}/></button><div className="form-grid"><label>Tool<Dropdown value={rule.tool_id} onChange={e => updateRule(index, { tool_id: e.target.value, write_scopes: tools.data?.find(tool => tool.tool_id === e.target.value)?.write_scopes.join(", ") ?? "" })}><option value="">Choose a registered tool</option>{tools.data?.map(tool => <option key={tool.tool_id} value={tool.tool_id}>{tool.label}</option>)}</Dropdown></label><label>Permission<Dropdown value={rule.effect} onChange={e => updateRule(index, { effect: e.target.value as PolicyRuleInput["effect"] })}><option value="allow">Allow</option><option value="approval_required">Require my approval</option><option value="deny">Deny</option></Dropdown></label></div>
          <fieldset><legend>Files this tool may read</legend>{artifacts.length ? artifacts.map(artifact => <label className="checkbox" key={artifact.artifact_id}><input type="checkbox" checked={rule.read_artifact_ids.includes(artifact.artifact_id)} onChange={e => updateRule(index, { read_artifact_ids: e.target.checked ? [...rule.read_artifact_ids, artifact.artifact_id] : rule.read_artifact_ids.filter(id => id !== artifact.artifact_id) })}/>{artifact.name}</label>) : <p className="muted">No inputs uploaded.</p>}</fieldset><label>Permitted write scopes<input value={rule.write_scopes} onChange={e => updateRule(index, { write_scopes: e.target.value })}/><span>Filled from the selected tool’s declared scopes. Edit to restrict access.</span></label><details><summary>Argument constraints</summary><textarea aria-label={`Argument constraints for rule ${index + 1}`} className="code-editor" value={rule.argument_constraints} onChange={e => updateRule(index, { argument_constraints: e.target.value })}/></details></fieldset>)}
          <button type="button" className="text-link" onClick={() => setRules(items => [...items, blankRule()])}><Plus size={16}/>Add permission</button><fieldset><legend>Execution limits</legend><div className="form-grid"><label>Maximum actions<input type="number" min="1" value={maxActions} onChange={e => setMaxActions(e.target.value)} required/></label><label>Runtime per action (ms)<input type="number" min="1" value={maxRuntime} onChange={e => setMaxRuntime(e.target.value)} required/></label><label>Output per action (bytes)<input type="number" min="1" value={maxOutput} onChange={e => setMaxOutput(e.target.value)} required/></label><label>Policy expiry (optional)<input type="datetime-local" value={expiry} onChange={e => setExpiry(e.target.value)}/></label></div></fieldset></>}
      </div></section></div>
      <aside className="review-sidebar"><p className="eyebrow">Before you begin</p><h2>Permission is the starting point.</h2><p>Your node signs this policy with the job. Changes require a new job.</p><dl className="definition-list"><dt>Inputs</dt><dd>{artifacts.length}</dd><dt>Provider</dt><dd>{providers.data?.find(item => item.provider_id === providerId)?.label ?? "Choose a provider"}</dd><dt>Policy</dt><dd>{rawMode ? "Custom JSON" : `${rules.length} permissions`}</dd></dl>{validation.length > 0 && <ul className="validation-summary">{validation.map(item => <li key={item}>{item}</li>)}</ul>}{formError && <p className="field-error" role="alert">{formError}</p>}<button className="button button-lime button-full" disabled={create.isPending || validation.length > 0}>{create.isPending ? "Signing job…" : "Create job"}</button><small>Confirmation and finality are reported by the network.</small></aside>
    </form></div>;
}
