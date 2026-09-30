import { useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import * as THREE from "three";

/** Decorative geometry, not a visualization of fabricated network activity. */
export default function BoundaryCube() {
  const host = useRef<HTMLDivElement>(null); const [paused, setPaused] = useState(false);
  useEffect(() => {
    const container = host.current!;
    let renderer: THREE.WebGLRenderer;
    try { renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" }); }
    catch { return; }
    const scene = new THREE.Scene(); const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 30);
    camera.position.set(4, 3.3, 5.5); camera.lookAt(0, 0, 0);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.setClearColor(0x000000, 0); container.appendChild(renderer.domElement); container.dataset.loaded = "true";
    const group = new THREE.Group(); scene.add(group);
    const geometry = new THREE.BoxGeometry(0.63, 0.63, 0.63);
    const edges = new THREE.EdgesGeometry(geometry);
    const material = new THREE.MeshStandardMaterial({ color: 0x151515, metalness: 0.4, roughness: 0.48 });
    const lineMaterial = new THREE.LineBasicMaterial({ color: 0x6a6a6a });
    for (let x = -1; x <= 1; x++) for (let y = -1; y <= 1; y++) for (let z = -1; z <= 1; z++) {
      const block = new THREE.Mesh(geometry, material); block.position.set(x * 0.71, y * 0.71, z * 0.71);
      block.add(new THREE.LineSegments(edges, lineMaterial)); group.add(block);
    }
    scene.add(new THREE.AmbientLight(0xffffff, 0.7));
    const key = new THREE.DirectionalLight(0xffffff, 5); key.position.set(2, 5, 4); scene.add(key);
    const rim = new THREE.DirectionalLight(0xffffff, 3); rim.position.set(-4, 1, -2); scene.add(rim);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)"); let visible = true;
    let previous = 0;
    const pointer = new THREE.Vector2();
    const hero = container.closest(".landing-hero") ?? container;
    const follow = (event: Event) => {
      const e = event as PointerEvent; if (e.pointerType !== "mouse") return;
      const rect = hero.getBoundingClientRect();
      pointer.set((e.clientX - rect.left) / rect.width * 2 - 1, (e.clientY - rect.top) / rect.height * 2 - 1);
    };
    const reset = () => pointer.set(0, 0);
    hero.addEventListener("pointermove", follow); hero.addEventListener("pointerleave", reset);
    const frame = (time: number) => {
      if (previous && !paused && !reduce.matches) group.rotation.y += Math.min((time - previous) / 1000, 0.05) * 0.13;
      if (!paused && !reduce.matches) {
        camera.position.x = THREE.MathUtils.lerp(camera.position.x, 4 + pointer.x * 1.8, 0.045);
        camera.position.y = THREE.MathUtils.lerp(camera.position.y, 3.3 - pointer.y * 1.5, 0.045);
        camera.lookAt(0, 0, 0);
      }
      previous = time; renderer.render(scene, camera);
    };
    const update = () => {
      previous = 0;
      renderer.setAnimationLoop(visible && !document.hidden && !paused && !reduce.matches ? frame : null);
      renderer.render(scene, camera);
    };
    const resize = new ResizeObserver(() => {
      const width = container.clientWidth, height = container.clientHeight;
      if (!width || !height) return;
      renderer.setSize(width, height); camera.aspect = width / height; camera.updateProjectionMatrix(); update();
    }); resize.observe(container);
    const observer = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; update(); }); observer.observe(container);
    document.addEventListener("visibilitychange", update); reduce.addEventListener("change", update); update();
    return () => {
      renderer.setAnimationLoop(null); resize.disconnect(); observer.disconnect();
      hero.removeEventListener("pointermove", follow); hero.removeEventListener("pointerleave", reset);
      document.removeEventListener("visibilitychange", update); reduce.removeEventListener("change", update);
      geometry.dispose(); edges.dispose(); material.dispose(); lineMaterial.dispose(); renderer.dispose(); renderer.domElement.remove(); delete container.dataset.loaded;
    };
  }, [paused]);
  return <div className="boundary-object"><div ref={host} className="cube-canvas" aria-hidden="true"><svg className="cube-fallback" viewBox="0 0 300 300"><path d="M150 35 255 95 255 210 150 270 45 210 45 95Z M45 95 150 155 255 95 M150 155V270 M150 35V155"/></svg></div><div className="cube-caption"><span>Autonomy, with boundaries.</span><button className="icon-button" onClick={() => setPaused(value => !value)} aria-label={paused ? "Play cube animation" : "Pause cube animation"}>{paused ? <Play size={15}/> : <Pause size={15}/>}</button></div></div>;
}
