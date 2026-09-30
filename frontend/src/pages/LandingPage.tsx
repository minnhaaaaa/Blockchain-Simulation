import { lazy, Suspense, useRef } from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowUpRight, GitBranch, LockKeyhole } from "lucide-react";
import { Brand } from "../components/Brand";
import { WordRotate } from "../components/ui/text-motion";
import { gsap, useGSAP } from "../components/Motion";
const BoundaryCube = lazy(() => import("../components/BoundaryCube"));

export function LandingPage() {
  const root = useRef<HTMLDivElement>(null);
  useGSAP(() => {
    const media = gsap.matchMedia();
    media.add("(prefers-reduced-motion: no-preference)", () => {
      const intro = gsap.timeline({ defaults: { ease: "power3.out" } });
      intro.from(".landing-nav", { autoAlpha: 0, y: -12, duration: 0.5 })
        .from(".hero-line", { yPercent: 105, duration: 0.9, stagger: 0.12 }, "-=0.2")
        .from(".hero-detail", { autoAlpha: 0, y: 18, duration: 0.65, stagger: 0.1 }, "-=0.55")
        .from(".permission-machine", { autoAlpha: 0, scale: 0.96, duration: 0.8 }, "-=0.6");
    });
    return () => media.revert();
  }, { scope: root });
  return <div ref={root} className="landing">
    <header className="landing-nav"><Brand/><nav aria-label="Main navigation"><a href="#how-it-works">How it works</a><a href="#your-control">Your control</a></nav><Link className="button button-ink" to="/sign-in">Sign in <ArrowUpRight size={16}/></Link></header>
    <main>
      <section className="landing-hero">
        <div className="hero-copy"><p className="eyebrow hero-detail"><span className="small-mark"/>Permission before execution.</p>
          <h1 aria-label="Let agents work. Keep the say."><span className="line-mask"><span className="hero-line">Let agents <WordRotate words={["work.", "read.", "think."]}/></span></span><span className="line-mask"><span className="hero-line">Keep the <em>say.</em></span></span></h1>
          <p className="hero-description hero-detail">Your files. Your boundaries. A shared record of every action. Give an agent room to work without handing over the keys.</p>
          <div className="hero-actions hero-detail"><Link className="button button-ink" to="/sign-in">Open your workspace <ArrowUpRight/></Link><a className="text-link" href="#how-it-works">Follow an action <ArrowDown size={16}/></a></div>
          <p className="hero-note hero-detail"><LockKeyhole size={14}/>You choose the model. You approve writes. Your network keeps the record.</p>
        </div>
        <div className="permission-machine"><Suspense fallback={<div className="cube-loading" aria-hidden="true"/>}><BoundaryCube/></Suspense></div>
      </section>
      <section className="landing-method" id="how-it-works"><div><p className="eyebrow">A clear chain of responsibility</p><h2>From “can it?”<br/>to “what happened?”</h2><p>One workspace connects the task, the decision, and the evidence behind it.</p></div><ol className="method-list"><li><span>Define</span><div><h3>Set the boundaries.</h3><p>Upload your inputs. Choose the tools and the exact files an action may touch.</p></div></li><li><span>Decide</span><div><h3>Keep a hand on the gate.</h3><p>Run permitted work, review sensitive requests, and see why an action was denied.</p></div></li><li><span>Inspect</span><div><h3>Follow the evidence.</h3><p>Inspect signed events, download actual outputs, and watch the network confirm the record.</p></div></li></ol></section>
      <section className="landing-control" id="your-control"><GitBranch size={36} strokeWidth={1.3}/><h2>Shared evidence.<br/>Independent nodes.</h2><p>Create a room. Discover its peers. Each node verifies the same signed history through Proof of Stake. Nothing appears in your dashboard until your network produces it.</p><Link className="button button-lime" to="/sign-in">Enter the workspace <ArrowUpRight/></Link></section>
    </main><footer className="landing-footer"><Brand/><span>A permission layer for accountable work.</span><a href="#how-it-works">Back to the process ↑</a></footer>
  </div>;
}
