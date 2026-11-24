import { motion } from "motion/react";
import { useState } from "react";
import type { AttendanceReport } from "@/lib/types";
import { cn, formatDayLong, weekdayShort } from "@/lib/utils";

const H = 168;
const PAD_TOP = 22;
const PAD_BOTTOM = 26;

/**
 * Oxirgi 7 kun: kelgan xodimlar soni (bitta seriya — legend shart emas, sarlavha nomlaydi).
 * Dataviz: ingichka ustunlar, bazaga tayangan 4px yumaloq uchlar, ustunlar orasida bo'shliq, hover tooltip.
 */
export function WeekChart({
  days,
  reports,
  selected,
  onSelect,
}: {
  days: string[];
  reports: (AttendanceReport | undefined)[];
  selected: string;
  onSelect: (day: string) => void;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const values = reports.map((r) => r?.summary.present ?? 0);
  const total = reports.find((r) => r)?.summary.total_employees ?? 0;
  const max = Math.max(1, total, ...values);
  const plotH = H - PAD_TOP - PAD_BOTTOM;
  const ticks = [0, Math.round(max / 2), max].filter((v, i, a) => a.indexOf(v) === i);

  return (
    <figure className="relative">
      <div className="relative" style={{ height: H }}>
        {/* Gridlines */}
        {ticks.map((t) => {
          const y = PAD_TOP + plotH - (t / max) * plotH;
          return (
            <div key={t} className="absolute inset-x-0 flex items-center gap-2" style={{ top: y }}>
              <span className="w-5 -translate-y-1/2 text-right font-mono text-[10px] text-fg-subtle tabular">{t}</span>
              <span className={cn("h-px flex-1 -translate-y-1/2", t === 0 ? "bg-line-strong" : "bg-[var(--color-grid)] opacity-60")} />
            </div>
          );
        })}

        <div className="absolute inset-y-0 right-0 left-7 grid grid-cols-7 gap-2 sm:gap-4">
          {days.map((d, i) => {
            const v = values[i] ?? 0;
            const h = (v / max) * plotH;
            const isSel = d === selected;
            const isHover = hover === i;
            const r = reports[i];
            return (
              <button
                key={d}
                onClick={() => onSelect(d)}
                onPointerEnter={() => setHover(i)}
                onPointerLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
                aria-label={`${formatDayLong(d)}: ${v} kishi kelgan`}
                aria-pressed={isSel}
                className="group relative h-full"
              >
                <span className="absolute inset-x-0 rounded-md transition-colors group-hover:bg-surface-2" style={{ top: PAD_TOP - 6, bottom: PAD_BOTTOM - 4 }} />
                <motion.span
                  className="absolute left-1/2 w-[34%] max-w-6 -translate-x-1/2 rounded-t-[4px]"
                  style={{
                    bottom: PAD_BOTTOM,
                    background: "var(--color-series-1)",
                    opacity: isSel || isHover ? 1 : 0.72,
                    boxShadow: isSel ? "0 0 0 2px var(--color-surface), 0 0 0 4px var(--color-series-1)" : undefined,
                  }}
                  initial={{ height: 0 }}
                  animate={{ height: Math.max(v ? 3 : 0, h) }}
                  transition={{ delay: i * 0.05, type: "spring", stiffness: 180, damping: 22 }}
                />
                {isSel || isHover ? (
                  <span className="absolute left-1/2 -translate-x-1/2 font-mono text-[11px] font-semibold text-fg tabular" style={{ bottom: PAD_BOTTOM + h + 4 }}>
                    {v}
                  </span>
                ) : null}
                <span className={cn("absolute inset-x-0 bottom-1 text-center text-[11px]", isSel ? "font-semibold text-fg" : "text-fg-subtle")}>
                  {weekdayShort(d)}
                </span>
                {isHover && r ? (
                  <span
                    role="tooltip"
                    className="pointer-events-none absolute left-1/2 z-10 w-44 -translate-x-1/2 rounded-lg border bg-surface-3 px-3 py-2 text-left text-[11px] shadow-pop"
                    style={{ bottom: PAD_BOTTOM + h + 24 }}
                  >
                    <span className="block font-semibold text-fg">{formatDayLong(d)}</span>
                    <span className="mt-1 flex justify-between text-fg-muted">Kelgan <b className="text-fg tabular">{v} / {r.summary.total_employees}</b></span>
                    <span className="flex justify-between text-fg-muted">Kechikkan <b className="text-fg tabular">{r.summary.late}</b></span>
                    <span className="flex justify-between text-fg-muted">Ofis vaqti <b className="text-fg tabular">{r.summary.total_office_hours} s</b></span>
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
      <figcaption className="sr-only">
        <table>
          <caption>Oxirgi 7 kunda kelgan xodimlar soni</caption>
          <tbody>
            {days.map((d, i) => (
              <tr key={d}>
                <th>{d}</th>
                <td>{values[i]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </figcaption>
    </figure>
  );
}
