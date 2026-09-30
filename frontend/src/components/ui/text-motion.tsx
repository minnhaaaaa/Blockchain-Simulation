import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useReducedMotion } from "./use-reduced-motion";

// Adapted from the supplied Magic UI Hyper Text / Word Rotate examples.
export function HyperText({ children }: { children: string }) {
  const [text, setText] = useState(children); const [run, setRun] = useState(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced || !run) return;
    let frame = 0; const start = performance.now();
    const animate = (now: number) => {
      const progress = Math.min(1, (now - start) / 550);
      setText(children.split("").map((letter, index) => index < progress * children.length || letter === " " ? letter : String.fromCharCode(65 + Math.floor(Math.random() * 26))).join(""));
      if (progress < 1) frame = requestAnimationFrame(animate);
    };
    frame = requestAnimationFrame(animate); return () => cancelAnimationFrame(frame);
  }, [children, run, reduced]);
  return <span className="hyper-text" onPointerEnter={() => setRun(value => value + 1)} aria-label={children}><span aria-hidden="true">{reduced ? children : text}</span></span>;
}
export function WordRotate({ words, duration = 2500 }: { words: string[]; duration?: number }) {
  const [index, setIndex] = useState(0); const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced || words.length < 2) return;
    const timer = setInterval(() => setIndex(value => (value + 1) % words.length), duration);
    return () => clearInterval(timer);
  }, [duration, words.length, reduced]);
  return <span className="word-rotate" aria-hidden="true"><span className="word-rotate-sizer">{words.reduce((a, b) => a.length > b.length ? a : b, "")}</span>
    <AnimatePresence mode="wait"><motion.span className="rotating-word" key={words[index % words.length]} initial={{ opacity: reduced ? 1 : 0, y: reduced ? 0 : "-80%" }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: reduced ? 0 : "80%" }} transition={{ duration: reduced ? 0 : 0.25 }}>{words[reduced ? 0 : index % words.length]}</motion.span></AnimatePresence>
  </span>;
}
