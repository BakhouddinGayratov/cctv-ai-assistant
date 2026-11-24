import { Expand, Pause, Play, ScanFace } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { api } from "@/lib/api";
import { useConfig, useWorkers } from "@/lib/queries";
import { channelLabel, cn } from "@/lib/utils";

const LAYOUTS = { "1": [1, 1], "4": [2, 2], "6": [3, 2], "9": [3, 3], "16": [4, 4] } as const;
type Layout = keyof typeof LAYOUTS;

function loadState(): { layout: Layout; channels: number[] } {
  try {
    const raw = JSON.parse(localStorage.getItem("cctv-grid") ?? "null") as { layout: Layout; channels: number[] } | null;
    if (raw && raw.layout in LAYOUTS && Array.isArray(raw.channels) && raw.channels.length >= 16) return raw;
  } catch {
    /* ignore */
  }
  return { layout: "4", channels: Array.from({ length: 16 }, (_, i) => i + 1) };
}

/**
 * Ko'p kamerali setka. Server barcha kameralarni bitta mozaika kadriga yig'ib uzatadi —
 * brauzer bitta ulanish ishlatadi (HTTP/1.1 da bir serverga 6 tadan ortiq oqim ochib bo'lmaydi).
 */
export function GridPage() {
  const config = useConfig();
  const workers = useWorkers();
  const cameras = config.data?.cameras ?? [];
  const [state, setState] = useState(loadState);
  const [playing, setPlaying] = useState(true);
  const [faces, setFaces] = useState(true);
  const [large, setLarge] = useState<number | null>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const [cols, rows] = large == null ? LAYOUTS[state.layout] : LAYOUTS["1"];
  const valid = cameras.map((c) => c.channel);
  // Tizimdan olingan kamera eski saqlangan setkada qolgan bo'lsa, bo'sh turgan boshqasi bilan almashtiriladi.
  const shown = large != null ? [large] : state.channels.slice(0, cols * rows).map((ch) => (valid.length && !valid.includes(ch) ? (valid.find((v) => !state.channels.includes(v)) ?? valid[0] ?? ch) : ch));

  const src = useMemo(
    () => (playing ? `/api/mosaic?channels=${shown.join(",")}&cols=${cols}&faces=${faces ? 1 : 0}&fps=5&t=${Date.now()}` : null),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [playing, shown.join(","), cols, faces],
  );

  useEffect(() => {
    try {
      localStorage.setItem("cctv-grid", JSON.stringify(state));
    } catch {
      /* ignore */
    }
  }, [state]);

  useEffect(() => {
    const stop = () => navigator.sendBeacon?.("/api/stream/stop?prefix=grid");
    window.addEventListener("pagehide", stop);
    return () => {
      window.removeEventListener("pagehide", stop);
      void api.stopStream("grid").catch(() => undefined);
    };
  }, []);

  function setChannel(slot: number, ch: number) {
    setState((s) => {
      const channels = [...s.channels];
      channels[slot] = ch;
      return { ...s, channels };
    });
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          ariaLabel="Maket"
          value={state.layout}
          onChange={(layout) => { setLarge(null); setState((s) => ({ ...s, layout })); }}
          options={(Object.keys(LAYOUTS) as Layout[]).map((k) => ({ value: k, label: k }))}
        />
        <Switch checked={faces} onChange={setFaces} label={<span className="flex items-center gap-1.5 text-xs"><ScanFace className="size-3.5" /> Odamlarni belgilash</span>} />
        <span className="hidden text-xs text-fg-subtle md:inline">Katakni bosing — kattalashadi</span>
        <div className="ml-auto flex gap-2">
          <Button size="icon-sm" variant="ghost" aria-label="To'liq ekran" onClick={() => void frameRef.current?.requestFullscreen?.()}>
            <Expand />
          </Button>
          {playing ? (
            <Button size="sm" variant="danger" onClick={() => { setPlaying(false); void api.stopStream("grid"); }}>
              <Pause /> To'xtatish
            </Button>
          ) : (
            <Button size="sm" variant="primary" onClick={() => setPlaying(true)}>
              <Play /> Ishga tushirish
            </Button>
          )}
        </div>
      </div>
      {workers.data && !workers.data.nvr_online ? (
        <p className="rounded-lg border border-critical/30 bg-critical-soft px-3 py-2 text-xs text-critical">Kameralar ulanmagan — tasvirlar ulanish tiklanganda o'zi paydo bo'ladi.</p>
      ) : null}

      <motion.div
        ref={frameRef}
        layout
        className="relative mx-auto w-full overflow-hidden rounded-2xl border bg-[#05070d] shadow-card"
        style={{ aspectRatio: `${cols * 16} / ${rows * 9}`, maxWidth: `calc((100dvh - 13rem) * ${(cols * 16) / (rows * 9)})` }}
      >
        {src ? <img key={src} src={src} alt="Kameralar setkasi" className="absolute inset-0 size-full" /> : (
          <div className="absolute inset-0 grid place-items-center text-sm text-white/50">To'xtatilgan</div>
        )}
        <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${cols}, 1fr)`, gridTemplateRows: `repeat(${rows}, 1fr)` }}>
          {shown.map((ch, i) => {
            const cam = cameras.find((c) => c.channel === ch);
            return (
              <div key={i} role="button" tabIndex={0} aria-label={large == null ? `${channelLabel(ch)} kameralarini kattalashtirish` : "Setkaga qaytish"} onClick={() => setLarge(large == null ? ch : null)} onKeyDown={(e) => e.key === "Enter" && e.target === e.currentTarget && setLarge(large == null ? ch : null)} className="group cursor-pointer relative border border-white/[0.06]">
                <div className="absolute inset-x-0 top-0 flex items-center gap-2 bg-gradient-to-b from-black/70 to-transparent p-1.5 sm:p-2">
                  <span className="shrink-0 whitespace-nowrap rounded bg-black/60 px-1.5 py-0.5 font-mono text-[10px] text-white">{channelLabel(ch)}</span>
                  <span className={cn("truncate text-[11px] font-medium text-white/90", cols >= 3 && "hidden sm:inline")}>{cam?.name}</span>
                </div>
                {large == null ? <div onClick={(e) => e.stopPropagation()} className={cn("absolute inset-x-0 bottom-0 flex gap-1.5 bg-gradient-to-t from-black/80 to-transparent p-2 opacity-0 transition-opacity group-focus-within:opacity-100 group-hover:opacity-100")}>
                  <select
                    value={ch}
                    onChange={(e) => setChannel(i, Number(e.target.value))}
                    aria-label={`${i + 1}-katak kamerasi`}
                    className="h-7 min-w-0 flex-1 rounded-md border border-white/15 bg-black/70 px-2 text-[11px] text-white"
                  >
                    {cameras.map((c) => (
                      <option key={c.channel} value={c.channel}>{channelLabel(c.channel)} · {c.name}</option>
                    ))}
                  </select>
                </div> : null}
              </div>
            );
          })}
        </div>
      </motion.div>
    </div>
  );
}
