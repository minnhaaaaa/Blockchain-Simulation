import { createContext, useContext, useEffect, useRef, useState, type PropsWithChildren } from "react";
import { AnimatePresence, motion, useMotionValue, useSpring, useTransform, type MotionValue } from "framer-motion";
import { useReducedMotion } from "./use-reduced-motion";

// Supplied dock adapted for semantic links, focus tooltips and reduced motion.
const DockContext = createContext<MotionValue<number> | null>(null);
const ItemContext = createContext(false);
export function Dock({ children }: PropsWithChildren) {
  const mouseX = useMotionValue(Infinity);
  const [open, setOpen] = useState(true); const host = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const cancel = () => clearTimeout(timer.current);
  const schedule = () => { cancel(); timer.current = setTimeout(() => {
    if (!host.current?.matches(":hover") && !host.current?.contains(document.activeElement)) setOpen(false);
  }, 1800); };
  useEffect(() => { const initial = setTimeout(() => {
    if (!host.current?.matches(":hover") && !host.current?.contains(document.activeElement)) setOpen(false);
  }, 2500); return () => { clearTimeout(initial); clearTimeout(timer.current); }; }, []);
  return <DockContext.Provider value={mouseX}><div ref={host} className={`dock-shell ${open ? "is-open" : "is-collapsed"}`}
    onPointerEnter={e => { if (e.pointerType === "mouse") { cancel(); setOpen(true); } }} onPointerLeave={schedule} onFocus={cancel}
    onBlur={schedule} onKeyDown={e => { if (e.key === "Escape") { host.current?.querySelector<HTMLButtonElement>(".dock-handle")?.focus(); setOpen(false); } }}>
    <button className="dock-handle" aria-label="Open navigation" aria-expanded={open} aria-controls="workspace-dock" onClick={() => setOpen(true)}><span/> <span className="dock-handle-label">Navigate</span></button>
    <nav id="workspace-dock" inert={!open} className="spring-dock" aria-label="Workspace navigation"
    onPointerMove={event => { if (event.pointerType === "mouse") mouseX.set(event.clientX); }}
    onPointerLeave={() => mouseX.set(Infinity)}>{children}</nav></div></DockContext.Provider>;
}
export function DockItem({ children }: PropsWithChildren) {
  const ref = useRef<HTMLDivElement>(null); const mouseX = useContext(DockContext)!;
  const [hovered, setHovered] = useState(false); const reduced = useReducedMotion();
  const distance = useTransform(mouseX, value => {
    const bounds = ref.current?.getBoundingClientRect();
    return bounds ? value - bounds.left - bounds.width / 2 : Infinity;
  });
  const target = useTransform(distance, [-150, 0, 150], [40, 64, 40]);
  const width = useSpring(target, { mass: 0.1, stiffness: 150, damping: 12 });
  return <ItemContext.Provider value={hovered}><motion.div ref={ref} className="spring-dock-item" style={{ width: reduced ? 40 : width }}
    onMouseEnter={() => setHovered(true)} onMouseLeave={() => setHovered(false)} onFocus={() => setHovered(true)} onBlur={() => setHovered(false)}>{children}</motion.div></ItemContext.Provider>;
}
export function DockIcon({ children }: PropsWithChildren) { return <span className="spring-dock-icon">{children}</span>; }
export function DockLabel({ children }: PropsWithChildren) {
  const hovered = useContext(ItemContext); const reduced = useReducedMotion();
  return <AnimatePresence>{hovered && <motion.span aria-hidden="true" className="spring-dock-label"
    initial={{ opacity: 0, y: reduced ? 0 : 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduced ? 0 : 4 }} transition={{ duration: reduced ? 0 : 0.15 }}>{children}</motion.span>}</AnimatePresence>;
}
