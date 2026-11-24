import { motion } from "motion/react";
import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface Column {
  key: string;
  label: string;
  value: number;
  tooltip?: ReactNode;
  muted?: boolean;
}

/**
 * Ustunli grafik (bitta seriya). Dataviz qoidalari: ingichka belgilar, bazaga tayangan 4px yumaloq uchlar,
 * yengil to'r, hover'da tooltip va qiymat, ekran o'quvchilar uchun yashirin jadval.
 */
export function ColumnChart({
  data,
  height = 180,
  color = "var(--color-series-1)",
  caption,
  labelEvery = 1,
}: {
  data: Column[];
  height?: number;
  color?: string;
  caption: string;
  labelEvery?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...data.map((d) => d.value));
  const top = 20;
  const bottom = 22;
  const plot = height - top - bottom;
  const ticks = [0, max / 2, max].map((v) => (max >= 10 ? Math.round(v) : Math.round(v * 10) / 10));

  return (
    <figure>
      <div className="relative" style={{ height }}>
        {ticks.map((t) => (
          <div key={t} className="absolute inset-x-0 flex items-center gap-2" style={{ top: top + plot - (t / max) * plot }}>
            <span className="w-7 -translate-y-1/2 text-right font-mono text-[10px] text-fg-subtle tabular">{t}</span>
            <span className={cn("h-px flex-1 -translate-y-1/2", t === 0 ? "bg-line-strong" : "bg-[var(--color-grid)] opacity-60")} />
          </div>
        ))}
        <div className="absolute inset-y-0 right-0 left-9 flex gap-[2px]">
          {data.map((d, i) => {
            const h = (d.value / max) * plot;
            const on = hover === i;
            return (
              <div
                key={d.key}
                className="group relative flex-1"
                onPointerEnter={() => setHover(i)}
                onPointerLeave={() => setHover(null)}
                tabIndex={0}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                aria-label={`${d.label}: ${d.value}`}
              >
                <span className="absolute inset-x-0 rounded transition-colors group-hover:bg-surface-2" style={{ top: top - 4, bottom: bottom - 2 }} />
                <motion.span
                  className="absolute left-1/2 w-[56%] max-w-6 min-w-[3px] -translate-x-1/2 rounded-t-[4px]"
                  style={{ bottom, background: color, opacity: d.muted ? 0.3 : on ? 1 : 0.8 }}
                  initial={{ height: 0 }}
                  animate={{ height: d.value ? Math.max(3, h) : 0 }}
                  transition={{ delay: Math.min(i, 30) * 0.015, type: "spring", stiffness: 170, damping: 22 }}
                />
                {on ? (
                  <span className="absolute left-1/2 -translate-x-1/2 font-mono text-[10px] font-semibold tabular" style={{ bottom: bottom + h + 3 }}>
                    {d.value}
                  </span>
                ) : null}
                {i % labelEvery === 0 ? (
                  <span className="absolute inset-x-0 bottom-1 truncate text-center text-[10px] text-fg-subtle">{d.label}</span>
                ) : null}
                {on && d.tooltip ? (
                  <span role="tooltip" className="pointer-events-none absolute left-1/2 z-10 w-44 -translate-x-1/2 rounded-lg border bg-surface-3 px-3 py-2 text-left text-[11px] shadow-pop" style={{ bottom: bottom + h + 20 }}>
                    {d.tooltip}
                  </span>
                ) : null}
              </div>
            );
          })}
        </div>
      </div>
      <figcaption className="sr-only">
        <table>
          <caption>{caption}</caption>
          <tbody>
            {data.map((d) => (
              <tr key={d.key}>
                <th>{d.label}</th>
                <td>{d.value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}

/** Gorizontal ustunlar ro'yxati — reyting uchun (qiymat matni har doim ko'rinadi). */
export function BarList({
  items,
  color = "var(--color-series-1)",
  unit = "",
}: {
  items: { key: string; label: ReactNode; value: number; sub?: ReactNode }[];
  color?: string;
  unit?: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul className="space-y-2.5">
      {items.map((it, i) => (
        <li key={it.key}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
            <span className="min-w-0 truncate font-medium">{it.label}</span>
            <span className="shrink-0 font-mono tabular text-fg-muted">
              {it.value}
              {unit}
              {it.sub ? <span className="ml-2 text-fg-subtle">{it.sub}</span> : null}
            </span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-surface-2">
            <motion.div
              className="h-full rounded-full"
              style={{ background: color }}
              initial={{ width: 0 }}
              animate={{ width: `${(it.value / max) * 100}%` }}
              transition={{ delay: i * 0.04, duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}
