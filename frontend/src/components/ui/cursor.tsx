import { createContext, useContext, useEffect, useState, type PropsWithChildren } from "react";
import { createPortal } from "react-dom";
import { motion, useMotionValue, useSpring, type MotionValue } from "framer-motion";
import { useReducedMotion } from "./use-reduced-motion";

// Animate UI Cursor API adapted to the existing Motion dependency.
// Keep the native pointer for precise clicking; the spring follower is decorative.
const Context = createContext<{ x: MotionValue<number>; y: MotionValue<number>; visible: boolean } | null>(null);
export function CursorProvider({ children, global = true }: PropsWithChildren<{ global?: boolean }>) {
  const x = useMotionValue(-100), y = useMotionValue(-100);
  const [visible, setVisible] = useState(false); const reduced = useReducedMotion();
  useEffect(() => {
    if (!global || reduced) return;
    const pointer = (event: PointerEvent) => {
      const target = event.target as Element;
      const enabled = event.pointerType === "mouse" && matchMedia("(pointer:fine)").matches && !target.closest("input,textarea,select,[role=combobox],[role=dialog],[role=listbox],[contenteditable=true],iframe");
      x.set(event.clientX); y.set(event.clientY); setVisible(enabled);
    };
    const hide = () => setVisible(false);
    window.addEventListener("pointermove", pointer); document.addEventListener("pointerleave", hide); window.addEventListener("blur", hide);
    return () => { window.removeEventListener("pointermove", pointer); document.removeEventListener("pointerleave", hide); window.removeEventListener("blur", hide); };
  }, [global, reduced, x, y]);
  return <Context.Provider value={{ x, y, visible: visible && !reduced }}>{children}</Context.Provider>;
}
export function Cursor() {
  const context = useContext(Context)!;
  return createPortal(<motion.div className="certa-cursor" aria-hidden="true" style={{ x: context.x, y: context.y, opacity: context.visible ? 1 : 0 }}/>, document.body);
}
export function CursorFollow({ children }: PropsWithChildren) {
  const context = useContext(Context)!;
  const x = useSpring(context.x, { stiffness: 500, damping: 50 }), y = useSpring(context.y, { stiffness: 500, damping: 50 });
  return createPortal(<motion.div className="certa-cursor-follow" aria-hidden="true" style={{ x, y, opacity: context.visible ? 1 : 0 }}>{children}</motion.div>, document.body);
}
