import { motion } from "motion/react";
import type { ReactNode } from "react";
import { cn, initials } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cn("skeleton rounded-lg", className)} />;
}

export function EmptyState({ icon, title, children, action }: { icon: ReactNode; title: ReactNode; children?: ReactNode; action?: ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className="flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed px-6 py-12 text-center"
    >
      <span className="grid size-12 place-items-center rounded-2xl bg-surface-2 text-fg-subtle [&_svg]:size-6">{icon}</span>
      <div>
        <p className="text-sm font-medium">{title}</p>
        {children ? <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-fg-muted">{children}</p> : null}
      </div>
      {action}
    </motion.div>
  );
}

const AVATAR_HUES = [285, 215, 160, 25, 330, 60, 250, 190];

export function Avatar({ name, src, size = 40, className }: { name: string; src?: string | null; size?: number; className?: string }) {
  const hue = AVATAR_HUES[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR_HUES.length];
  return src ? (
    <img
      src={src}
      alt={name}
      width={size}
      height={size}
      loading="lazy"
      className={cn("shrink-0 rounded-xl object-cover ring-1 ring-line", className)}
      style={{ width: size, height: size }}
    />
  ) : (
    <span
      aria-label={name}
      className={cn("grid shrink-0 place-items-center rounded-xl font-semibold text-white ring-1 ring-line", className)}
      style={{
        width: size,
        height: size,
        fontSize: size * 0.36,
        background: `linear-gradient(135deg, oklch(62% 0.17 ${hue}), oklch(48% 0.17 ${(hue ?? 0) + 40}))`,
      }}
    >
      {initials(name)}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded border bg-surface-2 px-1.5 py-0.5 font-mono text-[10px] text-fg-muted">{children}</kbd>;
}
