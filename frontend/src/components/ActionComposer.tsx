import { Dropdown } from "./ui/dropdown";
import { useState, type FormEvent } from "react";
import { Send } from "lucide-react";
import { useJobCommand, useTools } from "../api/hooks";
import type { ArtifactRef, ManualActionRequest, Tool } from "../types/api";
import { ErrorState, Skeleton } from "./States";

type FieldSchema = { type?: string; enum?: string[]; minimum?: number; format?: string; description?: string };
export function ActionComposer({ roomId, jobId, inputs }: { roomId: string; jobId: string; inputs: ArtifactRef[] }) {
  const tools = useTools(); const proposal = useJobCommand<ManualActionRequest>(roomId, jobId, "manual-actions");
  const [toolId, setToolId] = useState(""); const [args, setArgs] = useState<Record<string, unknown>>({}); const [inputIds, setInputIds] = useState<string[]>([]); const [output, setOutput] = useState(""); const [error, setError] = useState("");
  const tool: Tool | undefined = tools.data?.find(item => item.tool_id === toolId);
  const schema = tool?.argument_schema as { properties?: Record<string, FieldSchema>; required?: string[] } | undefined;
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setError("");
    try { await proposal.mutateAsync({ tool_id: toolId, arguments: args, input_artifact_ids: inputIds, expected_output_kind: output as ManualActionRequest["expected_output_kind"] }); setArgs({}); }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Could not propose the action."); }
  };
  if (tools.isPending) return <Skeleton/>;
  if (tools.error) return <ErrorState error={tools.error}/>;
  return <section className="surface action-composer"><div className="section-heading"><div><p className="eyebrow">Operator proposal</p><h2>What should happen next?</h2><p>Your node signs this request. The job’s policy decides whether it may run.</p></div><Send size={22}/></div>
    <form onSubmit={e => void submit(e)} className="form-stack"><label>Action tool<Dropdown value={toolId} onChange={e => { setToolId(e.target.value); setArgs({}); setInputIds([]); setOutput(tools.data?.find(item => item.tool_id === e.target.value)?.output_kinds[0] ?? ""); }} required><option value="">Choose a tool</option>{tools.data?.map(item => <option key={item.tool_id} value={item.tool_id}>{item.label}</option>)}</Dropdown></label>
      {tool && <><p className="muted">{tool.description}</p><div className="form-grid">{Object.entries(schema?.properties ?? {}).map(([key, field]) => <label key={key}>{key.replaceAll("_", " ")}
        {field.format === "uuid" && inputs.length ? <Dropdown value={String(args[key] ?? "")} required={schema?.required?.includes(key)} onChange={e => { setArgs(current => ({ ...current, [key]: e.target.value })); setInputIds(e.target.value ? [e.target.value] : []); }}><option value="">Choose an input</option>{inputs.map(item => <option key={item.artifact_id} value={item.artifact_id}>{item.name}</option>)}</Dropdown> : field.enum ? <Dropdown value={String(args[key] ?? "")} required={schema?.required?.includes(key)} onChange={e => setArgs(current => ({ ...current, [key]: e.target.value }))}><option value="">Choose {key.replaceAll("_", " ")}</option>{field.enum.map(value => <option key={value} value={value}>{value}</option>)}</Dropdown> : field.type === "integer" || field.type === "number" ? <input type="number" min={field.minimum} value={String(args[key] ?? "")} required={schema?.required?.includes(key)} onChange={e => setArgs(current => ({ ...current, [key]: Number(e.target.value) }))}/> : <textarea rows={3} value={String(args[key] ?? "")} required={schema?.required?.includes(key)} onChange={e => setArgs(current => ({ ...current, [key]: e.target.value }))}/>}
      </label>)}</div><label>Output kind<Dropdown value={output} onChange={e => setOutput(e.target.value)}>{tool.output_kinds.map(kind => <option key={kind}>{kind}</option>)}</Dropdown></label>
      <div className="scope-note"><strong>Declared writes</strong><span>{tool.write_scopes.length ? tool.write_scopes.join(", ") : "This tool does not write to a job workspace."}</span></div></>}
      {error && <p className="field-error" role="alert">{error}</p>}<button className="button button-ink" disabled={!tool || proposal.isPending}>{proposal.isPending ? "Evaluating request…" : "Propose action"}<Send size={16}/></button>
    </form></section>;
}
