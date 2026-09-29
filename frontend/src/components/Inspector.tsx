import { X } from "lucide-react";
import { useEffect, useRef, type PropsWithChildren } from "react";

export function Inspector({ title, open, onClose, children }: PropsWithChildren<{ title: string; open: boolean; onClose: () => void }>) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => { if (open) closeRef.current?.focus(); }, [open]);
  if (!open) return null;
  return <aside className="inspector" role="dialog" aria-modal="true" aria-label={title} onKeyDown={event => { if (event.key === "Escape") onClose(); }}>
    <header><h2>{title}</h2><button ref={closeRef} className="icon-button" aria-label="Close inspector" onClick={onClose}><X /></button></header>
    <div className="inspector-body">{children}</div>
  </aside>;
}
