import { motion } from "motion/react";
import { useMemo, useRef, type PointerEvent } from "react";
import type { TimelineData } from "@/lib/types";
import { cn } from "@/lib/utils";

const fmt = (min: number) => `${String(Math.floor(min / 60) % 24).padStart(2, "0")}:${String(Math.floor(min % 60)).padStart(2, "0")}`;
const toMin = (iso: string) => Number(iso.slice(11, 13)) * 60 + Number(iso.slice(14, 16)) + Number(iso.slice(17, 19) || 0) / 60;

/**
 * Kun chizig'i: NVR yozuvlari (kulrang — uzluksiz, yashil — harakat), faollik intensivligi (ko'k),
 * yuz ko'rinishlari (nuqtalar) va ogohlantirishlar (qizil uchburchak). Bosish/sudrash — vaqt tanlash.
 */
export function Timeline({
  data,
  window: [ws, we],
  cursor,
  onCursor,
}: {
  data: TimelineData | undefined;
  window: [number, number];
  cursor: number;
  onCursor: (minute: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);
  const span = we - ws;
  const pos = (m: number) => ((m - ws) / span) * 100;
  const inView = (m: number) => m >= ws && m <= we;

  const ticks = useMemo(() => {
    const step = span > 600 ? 120 : span > 240 ? 60 : span > 90 ? 15 : 5;
    const out: number[] = [];
    for (let m = Math.ceil(ws / step) * step; m <= we; m += step) out.push(m);
    return out;
  }, [ws, we, span]);

  const activity = useMemo(() => {
    const bucket = span > 600 ? 10 : span > 120 ? 2 : 1;
    const map = new Map<number, number>();
    for (const a of data?.activity ?? []) {
      const k = Math.floor(a.minute / bucket) * bucket;
      map.set(k, Math.max(map.get(k) ?? 0, a.motion));
    }
    const max = Math.max(0.01, ...map.values());
    return { bucket, items: [...map.entries()].filter(([k]) => k + bucket >= ws && k <= we).map(([k, v]) => ({ k, v: v / max })) };
  }, [data, ws, we, span]);

  function setFrom(e: PointerEvent) {
    const r = ref.current?.getBoundingClientRect();
    if (!r) return;
    const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    onCursor(ws + f * span);
  }

  return (
    <div className="select-none">
      <div
        ref={ref}
        role="slider"
        tabIndex={0}
        aria-label="Vaqt tanlash"
        aria-valuemin={ws}
        aria-valuemax={we}
        aria-valuenow={Math.round(cursor)}
        aria-valuetext={fmt(cursor)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") onCursor(Math.min(we, cursor + (e.shiftKey ? 10 : 1)));
          if (e.key === "ArrowLeft") onCursor(Math.max(ws, cursor - (e.shiftKey ? 10 : 1)));
        }}
        onPointerDown={(e) => {
          dragging.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
          setFrom(e);
        }}
        onPointerMove={(e) => dragging.current && setFrom(e)}
        onPointerUp={() => (dragging.current = false)}
        className="relative h-[124px] cursor-crosshair touch-none overflow-hidden rounded-xl border bg-surface-2"
      >
        {ticks.map((t) => (
          <span key={t} className="absolute inset-y-0 w-px bg-[var(--color-grid)] opacity-70" style={{ left: `${pos(t)}%` }} />
        ))}

        {/* 1-qator: NVR yozuvlari */}
        <span className="absolute top-2 left-2 text-[9px] font-medium tracking-wide text-fg-subtle uppercase">Yozuv</span>
        <div className="absolute inset-x-0 top-6 h-5">
          {data?.recordings_available ? (
            data.recordings?.map((r) => {
              const a = Math.max(ws, toMin(r.start));
              const b = Math.min(we, toMin(r.end) || 1440);
              if (b <= ws || a >= we) return null;
              return (
                <span
                  key={`${r.start}-${r.type}`}
                  title={`${r.start.slice(11, 19)} – ${r.end.slice(11, 19)} (${r.type === "motion" ? "harakat" : "uzluksiz"})`}
                  className={cn("absolute inset-y-0 rounded-sm", r.type === "motion" ? "bg-good/70" : "bg-fg-subtle/35")}
                  style={{ left: `${pos(a)}%`, width: `${Math.max(0.3, pos(b) - pos(a))}%` }}
                />
              );
            })
          ) : (
            <span className="absolute inset-0 grid place-items-center text-[10px] text-fg-subtle">Kameralar ulanmagan — yozuvlar ro'yxati yo'q</span>
          )}
        </div>

        {/* 2-qator: faollik */}
        <span className="absolute top-[52px] left-2 text-[9px] font-medium tracking-wide text-fg-subtle uppercase">Harakat</span>
        <div className="absolute inset-x-0 top-[66px] h-7">
          {activity.items.map(({ k, v }) => (
            <span
              key={k}
              className="absolute bottom-0 rounded-t-[2px]"
              style={{ left: `${pos(k)}%`, width: `${Math.max(0.25, (activity.bucket / span) * 100)}%`, height: `${Math.max(12, v * 100)}%`, background: "var(--color-series-1)", opacity: 0.35 + v * 0.65 }}
            />
          ))}
        </div>

        {/* 3-qator: yuzlar va ogohlantirishlar */}
        <div className="absolute inset-x-0 bottom-2 h-4">
          {(data?.sightings ?? []).filter((s) => inView(toMin(s.ts))).map((s) => (
            <span
              key={`${s.ts}-${s.name}`}
              title={`${s.ts.slice(11, 19)} · ${s.name}`}
              className={cn("absolute top-1/2 size-2 -translate-x-1/2 -translate-y-1/2 rounded-full ring-2 ring-surface-2", s.known ? "bg-good" : "bg-serious")}
              style={{ left: `${pos(toMin(s.ts))}%` }}
            />
          ))}
          {(data?.alerts ?? []).filter((a) => inView(toMin(a.ts))).map((a) => (
            <span key={a.id} title={`${a.ts.slice(11, 19)} · ${a.title}`} className="absolute -translate-x-1/2 text-[11px] leading-none text-critical" style={{ left: `${pos(toMin(a.ts))}%` }}>
              ▲
            </span>
          ))}
        </div>

        {/* kursor */}
        <motion.div className="pointer-events-none absolute inset-y-0 w-0.5 bg-brand shadow-[0_0_12px_var(--color-brand)]" animate={{ left: `${pos(cursor)}%` }} transition={{ type: "spring", stiffness: 600, damping: 45 }}>
          <span className="absolute top-0 left-1/2 -translate-x-1/2 rounded-b-md bg-brand px-1.5 py-0.5 font-mono text-[10px] text-white">{fmt(cursor)}</span>
        </motion.div>
      </div>
      <div className="relative mt-1 h-4">
        {ticks.map((t) => (
          <span key={t} className="absolute -translate-x-1/2 font-mono text-[10px] text-fg-subtle" style={{ left: `${pos(t)}%` }}>
            {fmt(t)}
          </span>
        ))}
      </div>
    </div>
  );
}

export { fmt as formatMinute };
