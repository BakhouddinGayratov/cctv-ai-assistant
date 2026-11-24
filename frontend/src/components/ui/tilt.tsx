import { motion, useMotionTemplate, useMotionValue, useReducedMotion, useSpring, useTransform } from "motion/react";
import type { ComponentProps, PointerEvent, ReactNode } from "react";
import { cn } from "@/lib/utils";

type TiltProps = Omit<ComponentProps<typeof motion.div>, "onPointerMove" | "onPointerLeave" | "children"> & {
  /** Maksimal og'ish burchagi (daraja). */
  max?: number;
  children: ReactNode;
};

/**
 * Sichqonchaga ergashuvchi 3D og'ish + yaltiroq nur.
 * Sensorli ekranlarda va "harakatni kamaytirish" yoqilganda o'chiq.
 */
export function Tilt({ max = 8, className, children, style, ...props }: TiltProps) {
  const reduce = useReducedMotion();
  const px = useMotionValue(0.5);
  const py = useMotionValue(0.5);
  const spring = { stiffness: 260, damping: 22, mass: 0.6 };
  const rotateX = useSpring(useTransform(py, [0, 1], [max, -max]), spring);
  const rotateY = useSpring(useTransform(px, [0, 1], [-max, max]), spring);
  const gx = useTransform(px, (v) => `${v * 100}%`);
  const gy = useTransform(py, (v) => `${v * 100}%`);
  const glare = useMotionTemplate`radial-gradient(420px circle at ${gx} ${gy}, oklch(100% 0 0 / 12%), transparent 45%)`;

  function onMove(e: PointerEvent<HTMLDivElement>) {
    if (reduce || e.pointerType !== "mouse") return;
    const r = e.currentTarget.getBoundingClientRect();
    px.set((e.clientX - r.left) / r.width);
    py.set((e.clientY - r.top) / r.height);
  }
  function onLeave() {
    px.set(0.5);
    py.set(0.5);
  }

  return (
    <motion.div
      className={cn("relative [transform-style:preserve-3d]", className)}
      style={{ rotateX, rotateY, transformPerspective: 900, ...style }}
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      {...props}
    >
      {children}
      <motion.div aria-hidden className="pointer-events-none absolute inset-0 rounded-[inherit]" style={{ background: glare }} />
    </motion.div>
  );
}
