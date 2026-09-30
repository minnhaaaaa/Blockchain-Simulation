import { FileCheck2, Paperclip, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { useUploadArtifact } from "../api/hooks";
import type { ArtifactRef } from "../types/api";
import { Copyable } from "./Copyable";

function fileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toLocaleString(undefined, { maximumFractionDigits: 1 })} KB`;
  return `${(bytes / (1024 * 1024)).toLocaleString(undefined, { maximumFractionDigits: 1 })} MB`;
}

export function ArtifactUploader({ artifacts, onChange, onBusyChange, compact = false }: { artifacts: ArtifactRef[]; onChange: (items: ArtifactRef[]) => void; onBusyChange?: (busy: boolean) => void; compact?: boolean }) {
  const input = useRef<HTMLInputElement>(null); const busyRef = useRef(false); const upload = useUploadArtifact();
  const [dragging, setDragging] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const submitFiles = async (files: FileList | File[]) => {
    if (busyRef.current) return;
    busyRef.current = true; setBusy(true); onBusyChange?.(true); setError("");
    const next = [...artifacts];
    try { for (const file of Array.from(files)) { next.push(await upload.mutateAsync(file)); onChange([...next]); } }
    catch (cause) { setError(cause instanceof Error ? cause.message : "Upload failed. Try the remaining files again."); }
    finally { busyRef.current = false; setBusy(false); onBusyChange?.(false); if (input.current) input.current.value = ""; }
  };
  return <div className={compact ? "compact-uploader" : ""}><div className={`drop-zone ${dragging ? "is-dragging" : ""}`} onDragOver={e => { e.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); void submitFiles(e.dataTransfer.files); }}>{!compact && <><Upload aria-hidden="true"/><strong>Bring your own inputs</strong><p>Drop files here, or choose them from your device.</p></>}<button type="button" className="button" disabled={busy} onClick={() => input.current?.click()}>{compact && <Paperclip size={16} aria-hidden="true"/>}{busy ? "Uploading…" : compact ? "Attach files" : "Choose files"}</button><input ref={input} className="sr-only" type="file" multiple disabled={busy} aria-label="Upload input files" onChange={e => { if (e.target.files) void submitFiles(e.target.files); }}/></div>
    {busy && <p role="status">Uploading and hashing your files…</p>}{error && <p className="field-error" role="alert">{error}</p>}
    <ul className="artifact-list">{artifacts.map(item => <li key={item.artifact_id}><FileCheck2 aria-hidden="true"/><span><strong title={item.name}>{item.name}</strong><small>{compact ? fileSize(item.size_bytes) : `${item.size_bytes.toLocaleString()} bytes · ${item.media_type}`}</small>{!compact && <Copyable value={item.sha256} label={`${item.name} hash`}/>}</span><button type="button" disabled={busy} className="icon-button" aria-label={`Remove ${item.name}`} onClick={() => onChange(artifacts.filter(candidate => candidate.artifact_id !== item.artifact_id))}><X size={16}/></button></li>)}</ul>
  </div>;
}
