import { X } from "lucide-react";
import { useEffect, useRef, type PropsWithChildren } from "react";

export function Inspector({ title, open, onClose, children }: PropsWithChildren<{ title: string; open: boolean; onClose: () => void }>) {
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (open && !dialog.current?.open) dialog.current?.showModal(); else if (!open && dialog.current?.open) dialog.current.close(); }, [open]);
  return <dialog ref={dialog} className="inspector" aria-label={title} onCancel={onClose} onClose={onClose}>
    <header><h2>{title}</h2><button className="icon-button" aria-label="Close inspector" onClick={onClose}><X /></button></header>
    <div className="inspector-body">{children}</div>
  </dialog>;
}
