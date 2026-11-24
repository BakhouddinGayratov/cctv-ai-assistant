import { Clapperboard, Download, Images, TimerReset } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { useLightbox } from "@/components/lightbox";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { Field, Input, Select } from "@/components/ui/field";
import { EmptyState } from "@/components/ui/misc";
import { api, b64Jpeg } from "@/lib/api";
import type { ArchiveClip, Camera } from "@/lib/types";
import { channelLabel, localIso } from "@/lib/utils";

const PRESETS = [
  { label: "1 daq oldin", back: 90, len: 30 },
  { label: "5 daq oldin", back: 5 * 60 + 30, len: 30 },
  { label: "15 daq oldin", back: 15 * 60 + 30, len: 30 },
  { label: "1 soat oldin", back: 3600 + 30, len: 30 },
] as const;

function rangeFromPreset(back: number, len: number): [string, string] {
  const start = new Date(Date.now() - back * 1000);
  return [localIso(start), localIso(new Date(start.getTime() + len * 1000))];
}

export function ArchiveSheet({
  open,
  onOpenChange,
  cameras,
  defaultChannel,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  cameras: Camera[];
  defaultChannel: number | null;
}) {
  const [channel, setChannel] = useState<number>(defaultChannel ?? cameras[0]?.channel ?? 1);
  const [[start, end], setRange] = useState<[string, string]>(() => rangeFromPreset(90, 30));
  const [frames, setFrames] = useState<string[] | null>(null);
  const [clip, setClip] = useState<ArchiveClip | null>(null);
  const [busy, setBusy] = useState<"frames" | "clip" | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const lightbox = useLightbox();

  useEffect(() => {
    if (open && defaultChannel != null) setChannel(defaultChannel);
  }, [open, defaultChannel]);

  useEffect(() => {
    if (busy !== "clip") return;
    setElapsed(0);
    const id = window.setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [busy]);

  useEffect(() => () => abortRef.current?.abort(), []);

  async function loadFrames() {
    setBusy("frames");
    setClip(null);
    try {
      const res = await api.archiveSnapshots(channel, start, end, 4);
      setFrames(res.frames_b64.map(b64Jpeg));
      if (!res.found) toast.warning("Bu oraliqda NVR arxividan kadr topilmadi");
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function loadClip() {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setBusy("clip");
    setFrames(null);
    setClip(null);
    const timeout = window.setTimeout(() => ctrl.abort(), 180_000);
    try {
      setClip(await api.archiveClip(channel, start, end, ctrl.signal));
      toast.success("Klip tayyor");
    } catch (e) {
      toast.error(ctrl.signal.aborted ? "Bekor qilindi yoki 3 daqiqadan oshdi" : (e as Error).message);
    } finally {
      window.clearTimeout(timeout);
      setBusy(null);
    }
  }

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title="NVR arxiv"
      description="NVR qattiq diskidagi yozuvdan istalgan lahzani ko'ring yoki 30 soniyagacha MP4 klip kesib oling."
    >
      <div className="space-y-5 p-6">
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="Kamera" className="sm:col-span-3">
            <Select value={channel} onChange={(e) => setChannel(Number(e.target.value))}>
              {cameras.map((c) => (
                <option key={c.channel} value={c.channel}>
                  {channelLabel(c.channel)} · {c.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Boshlanishi" className="sm:col-span-3 md:col-span-1">
            <Input type="datetime-local" step={1} value={start} onChange={(e) => setRange([e.target.value, end])} />
          </Field>
          <Field label="Tugashi" className="sm:col-span-3 md:col-span-1">
            <Input type="datetime-local" step={1} value={end} onChange={(e) => setRange([start, e.target.value])} />
          </Field>
          <Field label="Tezkor tanlov" className="sm:col-span-3 md:col-span-1">
            <Select
              defaultValue=""
              onChange={(e) => {
                const p = PRESETS[Number(e.target.value)];
                if (p) setRange(rangeFromPreset(p.back, p.len));
              }}
            >
              <option value="" disabled>
                Tanlang…
              </option>
              {PRESETS.map((p, i) => (
                <option key={p.label} value={i}>
                  {p.label} (30 s)
                </option>
              ))}
            </Select>
          </Field>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button onClick={loadFrames} loading={busy === "frames"} disabled={busy === "clip"}>
            <Images /> Kadrlarni ko'rish
          </Button>
          <Button variant="primary" onClick={loadClip} loading={busy === "clip"} disabled={busy === "frames"}>
            <Clapperboard /> MP4 klip (30 s gacha)
          </Button>
          {busy === "clip" ? (
            <Button variant="ghost" onClick={() => abortRef.current?.abort()}>
              <TimerReset /> Bekor qilish
            </Button>
          ) : null}
        </div>

        <AnimatePresence mode="wait">
          {busy === "clip" ? (
            <motion.div key="progress" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="rounded-xl border bg-surface-2 p-4">
              <div className="flex items-center justify-between text-sm">
                <span className="font-medium">NVR arxividan kesib olinmoqda…</span>
                <span className="font-mono tabular text-fg-muted">{elapsed}s</span>
              </div>
              <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-surface-3">
                <motion.div
                  className="h-full bg-brand-gradient"
                  initial={{ width: "2%" }}
                  animate={{ width: `${Math.min(95, 2 + elapsed * 1.1)}%` }}
                  transition={{ ease: "linear" }}
                />
              </div>
              <p className="mt-2 text-xs text-fg-subtle">Hikvision arxivni qidirishi 30–120 soniya olishi mumkin.</p>
            </motion.div>
          ) : clip ? (
            <motion.div key="clip" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="overflow-hidden rounded-xl border">
              <video src={clip.url} controls autoPlay className="aspect-video w-full bg-black" />
              <div className="flex items-center justify-between gap-2 bg-surface-2 px-4 py-2.5 text-xs">
                <span className="text-fg-muted">
                  {clip.camera_name} · {clip.start.slice(11, 19)} · {clip.seconds} s
                </span>
                <a href={clip.url} download className="flex items-center gap-1.5 font-medium text-brand hover:underline">
                  <Download className="size-3.5" /> Yuklab olish
                </a>
              </div>
            </motion.div>
          ) : frames ? (
            frames.length ? (
              <motion.ul key="frames" className="grid grid-cols-2 gap-3" initial="h" animate="s" variants={{ s: { transition: { staggerChildren: 0.06 } } }}>
                {frames.map((f, i) => (
                  <motion.li key={f.slice(-24)} variants={{ h: { opacity: 0, scale: 0.95 }, s: { opacity: 1, scale: 1 } }}>
                    <button onClick={() => lightbox.open(frames, i)} className="block overflow-hidden rounded-xl border transition hover:border-brand">
                      <img src={f} alt={`Arxiv kadri ${i + 1}`} className="aspect-video w-full object-cover" />
                    </button>
                  </motion.li>
                ))}
              </motion.ul>
            ) : (
              <EmptyState key="none" icon={<Images />} title="Kadr topilmadi">
                Bu vaqt oralig'ida NVR'da yozuv yo'q yoki NVR ulanmagan.
              </EmptyState>
            )
          ) : null}
        </AnimatePresence>
      </div>
    </Sheet>
  );
}
