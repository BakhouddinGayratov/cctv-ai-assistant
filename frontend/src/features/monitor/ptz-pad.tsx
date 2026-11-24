import { ArrowDown, ArrowLeft, ArrowRight, ArrowUp, Minus, Move, Plus } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { ext } from "@/lib/api";
import { usePtz } from "@/lib/queries";
import { cn } from "@/lib/utils";

function HoldButton({ label, onStart, onStop, children, className }: { label: string; onStart: () => void; onStop: () => void; children: ReactNode; className?: string }) {
  return (
    <button
      aria-label={label}
      onPointerDown={(e) => {
        e.currentTarget.setPointerCapture(e.pointerId);
        onStart();
      }}
      onPointerUp={onStop}
      onPointerCancel={onStop}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !e.repeat && onStart()}
      onKeyUp={(e) => (e.key === "Enter" || e.key === " ") && onStop()}
      className={cn("grid size-9 place-items-center rounded-lg bg-white/10 text-white transition hover:bg-white/20 active:scale-95 active:bg-brand", className)}
    >
      {children}
    </button>
  );
}

/** PTZ boshqaruvi — kamera PTZ'ni qo'llamasa umuman ko'rinmaydi. */
export function PtzPad({ channel }: { channel: number }) {
  const { data } = usePtz(channel);
  const [open, setOpen] = useState(false);
  if (!data?.supported) return null;

  const move = (pan: number, tilt: number, zoom: number) => () =>
    void ext.ptzMove(channel, pan, tilt, zoom).catch((e: Error) => toast.error(e.message));
  const stop = () => void ext.ptzStop(channel).catch(() => undefined);

  return (
    <div className="absolute right-3 bottom-3 flex flex-col items-end gap-2">
      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, scale: 0.9, y: 8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.9, y: 8 }}
            className="rounded-2xl border border-white/10 bg-black/70 p-2.5 backdrop-blur-md"
          >
            <div className="grid grid-cols-3 gap-1">
              <span />
              <HoldButton label="Yuqoriga" onStart={move(0, 50, 0)} onStop={stop}><ArrowUp className="size-4" /></HoldButton>
              <span />
              <HoldButton label="Chapga" onStart={move(-50, 0, 0)} onStop={stop}><ArrowLeft className="size-4" /></HoldButton>
              <span className="grid size-9 place-items-center text-white/40"><Move className="size-4" /></span>
              <HoldButton label="O'ngga" onStart={move(50, 0, 0)} onStop={stop}><ArrowRight className="size-4" /></HoldButton>
              <HoldButton label="Uzoqlashtirish" onStart={move(0, 0, -50)} onStop={stop}><Minus className="size-4" /></HoldButton>
              <HoldButton label="Pastga" onStart={move(0, -50, 0)} onStop={stop}><ArrowDown className="size-4" /></HoldButton>
              <HoldButton label="Yaqinlashtirish" onStart={move(0, 0, 50)} onStop={stop}><Plus className="size-4" /></HoldButton>
            </div>
            {data.presets.length ? (
              <select
                defaultValue=""
                onChange={(e) => e.target.value && void ext.ptzPreset(channel, Number(e.target.value)).catch((er: Error) => toast.error(er.message))}
                className="mt-2 h-8 w-full rounded-lg border border-white/15 bg-black/60 px-2 text-xs text-white"
                aria-label="Preset"
              >
                <option value="">Preset…</option>
                {data.presets.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              </select>
            ) : null}
          </motion.div>
        ) : null}
      </AnimatePresence>
      <button onClick={() => setOpen((o) => !o)} aria-expanded={open} className="flex items-center gap-1.5 rounded-lg border border-white/15 bg-black/60 px-2.5 py-1.5 text-xs text-white backdrop-blur hover:bg-black/80">
        <Move className="size-3.5" /> PTZ
      </button>
    </div>
  );
}
