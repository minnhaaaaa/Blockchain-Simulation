import { FileCheck2, Upload, X } from "lucide-react";
import { useRef, useState } from "react";
import { useUploadArtifact } from "../api/hooks";
import type { ArtifactRef } from "../types/api";
import { Copyable } from "./Copyable";

export function ArtifactUploader({ artifacts, onChange }: { artifacts: ArtifactRef[]; onChange: (items: ArtifactRef[]) => void }) {
  const inputRef = useRef<HTMLInputElement>(null); const upload = useUploadArtifact(); const [dragging, setDragging] = useState(false);
  const submitFiles = async (files: FileList | File[]) => { for (const file of Array.from(files)) { const result = await upload.mutateAsync(file); onChange([...artifacts, result]); } };
  return <div>
    <div className={`drop-zone ${dragging ? "is-dragging" : ""}`} onDragOver={event => { event.preventDefault(); setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={event => { event.preventDefault(); setDragging(false); void submitFiles(event.dataTransfer.files); }}>
      <Upload aria-hidden="true" /><p>Drop text or CSV inputs here</p><button type="button" className="button button-secondary" onClick={() => inputRef.current?.click()}>Choose files</button><input ref={inputRef} className="sr-only" type="file" multiple onChange={event => event.target.files && void submitFiles(event.target.files)} />
    </div>
    {upload.isPending && <p role="status">Uploading and hashing input…</p>}{upload.error && <p className="field-error" role="alert">{upload.error.message}</p>}
    <ul className="artifact-list">{artifacts.map(item => <li key={item.artifact_id}><FileCheck2 /><span><strong>{item.name}</strong><small>{item.size_bytes.toLocaleString()} bytes · {item.media_type}</small></span><Copyable value={item.artifact_id} label="artifact ID" /><button type="button" className="icon-button" aria-label={`Remove ${item.name}`} onClick={() => onChange(artifacts.filter(candidate => candidate.artifact_id !== item.artifact_id))}><X /></button></li>)}</ul>
  </div>;
}
