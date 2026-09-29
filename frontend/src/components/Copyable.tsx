import { Check, Copy } from "lucide-react";
import { useState } from "react";
import { shortId } from "../utils/format";

export function Copyable({ value, label = "identifier", compact = true }: { value: string; label?: string; compact?: boolean }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { await navigator.clipboard.writeText(value); setCopied(true); window.setTimeout(() => setCopied(false), 1400); };
  return <span className="copyable"><span className="mono" title={value} aria-label={`${label}: ${value}`}>{compact ? shortId(value, 14) : value}</span><button type="button" className="icon-button" aria-label={`Copy ${label}`} onClick={copy}>{copied ? <Check size={15} /> : <Copy size={15} />}</button><span className="sr-only" aria-live="polite">{copied ? `${label} copied` : ""}</span></span>;
}
