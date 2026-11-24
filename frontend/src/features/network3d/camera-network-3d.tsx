import { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import type { Camera } from "@/lib/types";
import { channelLabel } from "@/lib/utils";

const COLORS = {
  core: new THREE.Color("#7c6cff"),
  entrance: new THREE.Color("#19c26b"),
  desk: new THREE.Color("#22d3ee"),
  camera: new THREE.Color("#8b7dff"),
  selected: new THREE.Color("#ffffff"),
};

interface NodeInfo {
  channel: number;
  mesh: THREE.Mesh;
  halo: THREE.Mesh;
  base: THREE.Color;
  pos: THREE.Vector3;
}

/** Fibonacci sferasi — tugunlar teng taqsimlanadi. */
function spherePoints(n: number, r: number): THREE.Vector3[] {
  const pts: THREE.Vector3[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;
    const rad = Math.sqrt(1 - y * y);
    const t = golden * i;
    pts.push(new THREE.Vector3(Math.cos(t) * rad * r, y * r * 0.72, Math.sin(t) * rad * r));
  }
  return pts;
}

export default function CameraNetwork3D({
  cameras,
  selected,
  onSelect,
}: {
  cameras: Camera[];
  selected: number | null;
  onSelect: (ch: number) => void;
}) {
  const hostRef = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const selectedRef = useRef(selected);
  const onSelectRef = useRef(onSelect);
  const [hovered, setHovered] = useState<Camera | null>(null);
  selectedRef.current = selected;
  onSelectRef.current = onSelect;

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    host.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x070a12, 0.035);
    const camera3 = new THREE.PerspectiveCamera(42, 1, 0.1, 100);
    camera3.position.set(0, 2.6, 9.5);

    const controls = new OrbitControls(camera3, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 6;
    controls.maxDistance = 14;
    controls.autoRotate = !reduce;
    controls.autoRotateSpeed = 0.6;

    scene.add(new THREE.AmbientLight(0xffffff, 0.55));
    const key = new THREE.PointLight(0x8b7dff, 40, 30);
    key.position.set(4, 5, 6);
    scene.add(key);
    const rim = new THREE.PointLight(0x22d3ee, 25, 30);
    rim.position.set(-6, -3, -4);
    scene.add(rim);

    const world = new THREE.Group();
    scene.add(world);

    // Markaz: NVR yadrosi
    const coreGeo = new THREE.IcosahedronGeometry(0.85, 1);
    const coreMat = new THREE.MeshStandardMaterial({ color: COLORS.core, emissive: COLORS.core, emissiveIntensity: 0.55, roughness: 0.35, metalness: 0.4, flatShading: true });
    const core = new THREE.Mesh(coreGeo, coreMat);
    world.add(core);
    const wireGeo = new THREE.IcosahedronGeometry(1.25, 1);
    const wireMat = new THREE.MeshBasicMaterial({ color: COLORS.core, wireframe: true, transparent: true, opacity: 0.22 });
    const wire = new THREE.Mesh(wireGeo, wireMat);
    world.add(wire);

    // Orbitlar (bezak halqalari)
    const ringMat = new THREE.MeshBasicMaterial({ color: 0x8b7dff, transparent: true, opacity: 0.12, side: THREE.DoubleSide });
    const rings = [2.2, 3.6].map((r, i) => {
      const m = new THREE.Mesh(new THREE.RingGeometry(r, r + 0.012, 128), ringMat);
      m.rotation.x = Math.PI / 2 + (i ? 0.35 : -0.2);
      world.add(m);
      return m;
    });

    // Kamera tugunlari
    const points = spherePoints(cameras.length, 3.6);
    const nodeGeo = new THREE.OctahedronGeometry(0.2, 0);
    const haloGeo = new THREE.RingGeometry(0.3, 0.36, 40);
    const nodes: NodeInfo[] = cameras.map((cam, i) => {
      const base = cam.roles.includes("entrance") ? COLORS.entrance : cam.roles.includes("desk") ? COLORS.desk : COLORS.camera;
      const mesh = new THREE.Mesh(
        nodeGeo,
        new THREE.MeshStandardMaterial({ color: base, emissive: base, emissiveIntensity: 0.7, roughness: 0.3, metalness: 0.2 }),
      );
      const pos = points[i] ?? new THREE.Vector3();
      mesh.position.copy(pos);
      mesh.userData.channel = cam.channel;
      const halo = new THREE.Mesh(haloGeo, new THREE.MeshBasicMaterial({ color: base, transparent: true, opacity: 0.45, side: THREE.DoubleSide }));
      halo.position.copy(pos);
      halo.userData.channel = cam.channel;
      world.add(mesh, halo);
      return { channel: cam.channel, mesh, halo, base, pos };
    });

    // Yadrodan tugunlarga chiziqlar
    const lineGeo = new THREE.BufferGeometry().setFromPoints(nodes.flatMap((n) => [new THREE.Vector3(), n.pos]));
    const lineMat = new THREE.LineBasicMaterial({ color: 0x8b7dff, transparent: true, opacity: 0.18 });
    world.add(new THREE.LineSegments(lineGeo, lineMat));

    // Ma'lumot impulslari
    const pulseGeo = new THREE.SphereGeometry(0.045, 8, 8);
    const pulses = nodes.map((n, i) => {
      const m = new THREE.Mesh(pulseGeo, new THREE.MeshBasicMaterial({ color: n.base, transparent: true, opacity: 0.9 }));
      m.userData = { node: n, t: (i * 0.137) % 1, speed: 0.18 + (i % 5) * 0.04 };
      world.add(m);
      return m;
    });

    // Yulduz changlari
    const dustGeo = new THREE.BufferGeometry();
    const dust = new Float32Array(600 * 3);
    for (let i = 0; i < dust.length; i++) dust[i] = (Math.random() - 0.5) * 30;
    dustGeo.setAttribute("position", new THREE.BufferAttribute(dust, 3));
    const dustMat = new THREE.PointsMaterial({ color: 0x9aa4ff, size: 0.03, transparent: true, opacity: 0.5 });
    scene.add(new THREE.Points(dustGeo, dustMat));

    // O'lcham
    const resize = () => {
      const w = host.clientWidth;
      const h = host.clientHeight;
      renderer.setSize(w, h, false);
      renderer.domElement.style.width = `${w}px`;
      renderer.domElement.style.height = `${h}px`;
      camera3.aspect = w / Math.max(1, h);
      camera3.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize);
    ro.observe(host);
    resize();

    // Hover / bosish (raycasting)
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2(9, 9);
    let hoverCh: number | null = null;
    let downAt = { x: 0, y: 0 };
    const meshes = nodes.flatMap((n) => [n.mesh, n.halo]);
    const onMove = (e: PointerEvent) => {
      const r = renderer.domElement.getBoundingClientRect();
      pointer.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
    };
    const onLeave = () => pointer.set(9, 9);
    const onDown = (e: PointerEvent) => (downAt = { x: e.clientX, y: e.clientY });
    const onUp = (e: PointerEvent) => {
      if (Math.hypot(e.clientX - downAt.x, e.clientY - downAt.y) > 5) return; // aylantirish, bosish emas
      onMove(e);
      raycaster.setFromCamera(pointer, camera3);
      const hit = raycaster.intersectObjects(meshes, false)[0];
      if (hit) onSelectRef.current(hit.object.userData.channel as number);
    };
    renderer.domElement.addEventListener("pointermove", onMove);
    renderer.domElement.addEventListener("pointerleave", onLeave);
    renderer.domElement.addEventListener("pointerdown", onDown);
    renderer.domElement.addEventListener("pointerup", onUp);

    // Faqat ko'rinib turganda render qilish
    let visible = true;
    const io = new IntersectionObserver(([entry]) => (visible = entry?.isIntersecting ?? true));
    io.observe(host);

    const clock = new THREE.Clock();
    const tmp = new THREE.Vector3();
    let raf = 0;
    const loop = () => {
      raf = requestAnimationFrame(loop);
      if (!visible || document.hidden) return;
      const dt = Math.min(clock.getDelta(), 0.05);
      const t = clock.elapsedTime;
      controls.update();

      if (!reduce) {
        core.rotation.y += dt * 0.35;
        core.rotation.x += dt * 0.12;
        wire.rotation.y -= dt * 0.2;
        rings.forEach((r, i) => (r.rotation.z += dt * (i ? -0.08 : 0.06)));
        for (const p of pulses) {
          const d = p.userData as { node: NodeInfo; t: number; speed: number };
          d.t = (d.t + dt * d.speed) % 1;
          p.position.copy(tmp.set(0, 0, 0).lerp(d.node.pos, d.t));
          (p.material as THREE.MeshBasicMaterial).opacity = Math.sin(d.t * Math.PI) * 0.9;
        }
      }

      raycaster.setFromCamera(pointer, camera3);
      const hit = raycaster.intersectObjects(meshes, false)[0];
      const ch = hit ? (hit.object.userData.channel as number) : null;
      if (ch !== hoverCh) {
        hoverCh = ch;
        renderer.domElement.style.cursor = ch != null ? "pointer" : "grab";
        controls.autoRotate = ch == null && !reduce;
        setHovered(ch != null ? (cameras.find((c) => c.channel === ch) ?? null) : null);
      }

      for (const n of nodes) {
        const isSel = n.channel === selectedRef.current;
        const isHover = n.channel === hoverCh;
        const target = isSel ? 1.9 : isHover ? 1.5 : 1;
        n.mesh.scale.lerp(tmp.setScalar(target), 0.15);
        n.mesh.rotation.y += dt * (isSel ? 2 : 0.6);
        n.halo.lookAt(camera3.position);
        const pulse = isSel ? 1.4 + Math.sin(t * 4) * 0.25 : 1;
        n.halo.scale.setScalar(pulse * (isHover ? 1.3 : 1));
        const mat = n.mesh.material as THREE.MeshStandardMaterial;
        mat.emissive.copy(isSel ? COLORS.selected : n.base);
        mat.emissiveIntensity = isSel ? 0.9 : isHover ? 1 : 0.7;
      }

      // Hover yorlig'i — DOM pozitsiyasi (React qayta render qilinmaydi)
      const label = labelRef.current;
      const focus = nodes.find((n) => n.channel === hoverCh);
      if (label) {
        if (focus) {
          focus.mesh.getWorldPosition(tmp).project(camera3);
          const x = (tmp.x * 0.5 + 0.5) * host.clientWidth;
          const y = (-tmp.y * 0.5 + 0.5) * host.clientHeight;
          label.style.transform = `translate(${x}px, ${y - 18}px) translate(-50%, -100%)`;
          label.style.opacity = "1";
        } else {
          label.style.opacity = "0";
        }
      }

      renderer.render(scene, camera3);
    };
    loop();

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      io.disconnect();
      controls.dispose();
      renderer.domElement.removeEventListener("pointermove", onMove);
      renderer.domElement.removeEventListener("pointerleave", onLeave);
      renderer.domElement.removeEventListener("pointerdown", onDown);
      renderer.domElement.removeEventListener("pointerup", onUp);
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose();
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach((x) => x.dispose());
        else mat?.dispose();
      });
      renderer.dispose();
      renderer.domElement.remove();
    };
  }, [cameras]);

  return (
    <div className="relative h-[380px] overflow-hidden rounded-xl border bg-[radial-gradient(circle_at_50%_45%,oklch(30%_0.1_285/55%),#070a12_70%)] sm:h-[440px]">
      <div ref={hostRef} className="absolute inset-0" />
      <div
        ref={labelRef}
        className="pointer-events-none absolute top-0 left-0 rounded-lg border border-white/15 bg-black/70 px-2.5 py-1.5 text-xs whitespace-nowrap text-white opacity-0 shadow-xl backdrop-blur transition-opacity duration-150"
      >
        {hovered ? (
          <>
            <span className="font-mono text-white/60">{channelLabel(hovered.channel)}</span> · <span className="font-medium">{hovered.name}</span>
          </>
        ) : null}
      </div>
      <div className="pointer-events-none absolute bottom-3 left-3 flex flex-wrap gap-3 rounded-lg bg-black/45 px-3 py-2 text-[11px] text-white/80 backdrop-blur">
        <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-[#19c26b]" /> Kirish</span>
        <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-[#22d3ee]" /> Ish joyi</span>
        <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-[#8b7dff]" /> Boshqa</span>
      </div>
      <p className="pointer-events-none absolute top-3 right-3 rounded-lg bg-black/45 px-2.5 py-1.5 text-[11px] text-white/70 backdrop-blur">
        Aylantiring · tugunni bosing
      </p>
    </div>
  );
}
