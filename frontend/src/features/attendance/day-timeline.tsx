import { motion } from "motion/react";
import type { AttendanceRow } from "@/lib/types";
import { hhmm, hourOf, localIso } from "@/lib/utils";

function pct(iso: string, [a, b]: [number, number]) {
  return Math.min(100, Math.max(0, ((hourOf(iso) - a) / (b - a)) * 100));
}

/** Ofisdagi oraliqlar (ko'k), ish stoli tekshiruvlari (aqua / kulrang), kirish ▼ va chiqish ▲. */
export function DayTimeline({ row, window: win, live }: { row: AttendanceRow; window: [number, number]; live: boolean }) {
  const spans: { from: string; to: string }[] = [];
  let inAt: string | null = null;
  for (const p of row.passages) {
    if (p.direction === "IN" && inAt === null) inAt = p.ts;
    else if (p.direction === "OUT" && inAt !== null) {
      spans.push({ from: inAt, to: p.ts });
      inAt = null;
    }
  }
  if (inAt !== null && live) spans.push({ from: inAt, to: localIso(new Date()) });

  const hours: number[] = [];
  for (let h = Math.ceil(win[0]); h <= Math.floor(win[1]); h += 3) hours.push(h);

  return (
    <div className="relative h-7 w-full min-w-[220px] overflow-hidden rounded-md border bg-surface-2" role="img" aria-label={`${row.name} kun chizig'i`}>
      {hours.map((h) => (
        <span key={h} className="absolute inset-y-0 w-px bg-[var(--color-grid)] opacity-50" style={{ left: `${((h - win[0]) / (win[1] - win[0])) * 100}%` }} />
      ))}
      {spans.map((s) => {
        const left = pct(s.from, win);
        return (
          <motion.span
            key={s.from}
            title={`Ofisda: ${hhmm(s.from)} – ${hhmm(s.to)}`}
            className="absolute top-1 bottom-1 origin-left rounded-[4px]"
            style={{ left: `${left}%`, width: `${Math.max(0.6, pct(s.to, win) - left)}%`, background: "color-mix(in oklab, var(--color-series-1) 55%, transparent)" }}
            initial={{ scaleX: 0 }}
            animate={{ scaleX: 1 }}
            transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          />
        );
      })}
      {row.desk_timeline.map((d) => (
        <span
          key={d.ts}
          title={`${hhmm(d.ts)} — ${d.present ? "ish joyida" : "ish joyida yo'q"}`}
          className="absolute top-1.5 bottom-1.5 w-[3px] rounded-full"
          style={{ left: `${pct(d.ts, win)}%`, background: d.present ? "var(--color-series-3)" : "var(--color-fg-subtle)", opacity: d.present ? 1 : 0.45 }}
        />
      ))}
      {row.passages.map((p) => (
        <span
          key={p.ts}
          title={`${hhmm(p.ts)} — ${p.direction === "IN" ? "kirdi" : "chiqdi"}`}
          className="absolute top-0 -translate-x-1/2 text-[9px] leading-none"
          style={{ left: `${pct(p.ts, win)}%`, color: p.direction === "IN" ? "var(--color-good)" : "var(--color-serious)" }}
        >
          {p.direction === "IN" ? "▼" : "▲"}
        </span>
      ))}
    </div>
  );
}
