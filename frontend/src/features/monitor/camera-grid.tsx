import { DoorOpen, Monitor, Video } from "lucide-react";
import { motion } from "motion/react";
import { memo, useEffect, useState } from "react";
import { Tilt } from "@/components/ui/tilt";
import type { Camera } from "@/lib/types";
import { channelLabel, cn } from "@/lib/utils";

/** Kadrlarni 3 tadan navbat bilan yuklaydi — barcha RTSP'ni bir vaqtda ochmaslik uchun. */
export function usePreviewStills(channels: number[], enabled: boolean) {
  const [stills, setStills] = useState<Record<number, string>>({});

  useEffect(() => {
    if (!enabled) return;
    const ctrl = new AbortController();
    const urls: string[] = [];
    const queue = [...channels];
    async function worker() {
      while (queue.length && !ctrl.signal.aborted) {
        const ch = queue.shift() as number;
        try {
          const res = await fetch(`/api/snapshot/${ch}?t=${Date.now()}`, { signal: ctrl.signal });
          if (!res.ok) continue;
          const url = URL.createObjectURL(await res.blob());
          urls.push(url);
          setStills((s) => ({ ...s, [ch]: url }));
        } catch {
          /* bekor qilindi yoki kamera javob bermadi */
        }
      }
    }
    void Promise.all([worker(), worker(), worker()]);
    return () => {
      ctrl.abort();
      for (const u of urls) URL.revokeObjectURL(u);
      setStills({});
    };
  }, [channels, enabled]);

  return stills;
}

const Tile = memo(function Tile({
  camera,
  active,
  still,
  index,
  onSelect,
}: {
  camera: Camera;
  active: boolean;
  still: string | undefined;
  index: number;
  onSelect: (ch: number) => void;
}) {
  const entrance = camera.roles.includes("entrance");
  const desk = camera.roles.includes("desk");
  return (
    <motion.li
      initial={{ opacity: 0, y: 12, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ delay: index * 0.025, duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
    >
      <Tilt max={10} className="rounded-xl">
        <button
          onClick={() => onSelect(camera.channel)}
          aria-pressed={active}
          aria-label={`${camera.name}, ${channelLabel(camera.channel)}`}
          className={cn(
            "group block w-full overflow-hidden rounded-xl border bg-surface-2 text-left transition-[border-color,box-shadow] duration-300",
            active ? "border-brand shadow-glow" : "hover:border-line-strong",
          )}
        >
          <div className="relative aspect-video overflow-hidden bg-[#070a12]">
            {still ? (
              <img src={still} alt="" className="size-full object-cover transition-transform duration-500 group-hover:scale-105" />
            ) : (
              <div className="grid size-full place-items-center bg-[radial-gradient(circle_at_50%_120%,oklch(40%_0.1_285/40%),transparent_70%)]">
                <Video className="size-6 text-white/25 transition-transform duration-300 group-hover:scale-110 group-hover:text-white/50" />
              </div>
            )}
            <span className="absolute top-1.5 left-1.5 rounded-md bg-black/65 px-1.5 py-0.5 font-mono text-[10px] text-white/90 backdrop-blur">
              {channelLabel(camera.channel)}
            </span>
            <span className="absolute top-1.5 right-1.5 flex gap-1">
              {entrance ? (
                <span title="Kirish kamerasi (davomat)" className="grid size-5 place-items-center rounded-md bg-good/85 text-white">
                  <DoorOpen className="size-3" />
                </span>
              ) : null}
              {desk ? (
                <span title="Ish joyi kamerasi" className="grid size-5 place-items-center rounded-md bg-accent/85 text-black">
                  <Monitor className="size-3" />
                </span>
              ) : null}
            </span>
            {active ? <span className="absolute inset-x-0 bottom-0 h-0.5 bg-brand-gradient" /> : null}
          </div>
          <p className="truncate px-2.5 py-2 text-xs font-medium">{camera.name}</p>
        </button>
      </Tilt>
    </motion.li>
  );
});

export function CameraGrid({
  cameras,
  selected,
  onSelect,
  stills,
}: {
  cameras: Camera[];
  selected: number | null;
  onSelect: (ch: number) => void;
  stills: Record<number, string>;
}) {
  return (
    <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 2xl:grid-cols-6">
      {cameras.map((c, i) => (
        <Tile key={c.channel} camera={c} active={c.channel === selected} still={stills[c.channel]} index={i} onSelect={onSelect} />
      ))}
    </ul>
  );
}
