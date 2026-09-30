import { useRef, type PropsWithChildren } from "react";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";

gsap.registerPlugin(useGSAP);

export function Reveal({ children, className = "" }: PropsWithChildren<{ className?: string }>) {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(() => {
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      gsap.from(root.current, { autoAlpha: 0, y: 16, duration: 0.5, ease: "power3.out", clearProps: "all" });
    });
    return () => media.revert();
  }, { scope: root });
  return <div ref={root} className={className}>{children}</div>;
}

export { gsap, useGSAP };
