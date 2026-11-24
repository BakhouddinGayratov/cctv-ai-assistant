import { motion } from "motion/react";
import type { ReactNode } from "react";
import { CountUp } from "@/components/ui/count-up";
import { Skeleton } from "@/components/ui/misc";
import { Tilt } from "@/components/ui/tilt";
import { cn } from "@/lib/utils";

const TONES = {
  brand: "text-brand bg-brand-soft",
  accent: "text-accent bg-accent-soft",
  good: "text-good bg-good-soft",
  warning: "text-warning bg-warning-soft",
  critical: "text-critical bg-critical-soft",
} as const;

export function StatTile({
  icon,
  label,
  value,
  suffix,
  hint,
  tone = "brand",
  decimals = 0,
  loading,
  index = 0,
}: {
  icon: ReactNode;
  label: string;
  value: number;
  suffix?: ReactNode;
  hint?: ReactNode;
  tone?: keyof typeof TONES;
  decimals?: number;
  loading?: boolean;
  index?: number;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.06, duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
    >
      <Tilt max={6} className="card h-full overflow-hidden p-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-medium text-fg-muted">{label}</span>
          <span className={cn("grid size-8 place-items-center rounded-lg [&_svg]:size-4", TONES[tone])}>{icon}</span>
        </div>
        {loading ? (
          <Skeleton className="mt-3 h-8 w-20" />
        ) : (
          <p className="mt-2 text-[28px] leading-none font-semibold tracking-tight">
            <CountUp value={value} decimals={decimals} />
            {suffix ? <span className="ml-1 text-sm font-medium text-fg-subtle">{suffix}</span> : null}
          </p>
        )}
        {hint ? <p className="mt-2 truncate text-[11px] text-fg-subtle">{hint}</p> : null}
      </Tilt>
    </motion.div>
  );
}
