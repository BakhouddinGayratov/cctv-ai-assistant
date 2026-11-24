import { useMutation } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, Clapperboard, Film, Images, ListVideo, Search, Sparkles, ZoomIn } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { toast } from "sonner";
import { JobProgress } from "@/components/job-progress";
import { useLightbox } from "@/components/lightbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { api, b64Jpeg, ext } from "@/lib/api";
import { useConfig, useJobs, useTimeline } from "@/lib/queries";
import type { JobInfo, SearchHit } from "@/lib/types";
import { channelLabel, formatDayLong, shiftDate, todayIso } from "@/lib/utils";
import { formatMinute, Timeline } from "./timeline";

const ZOOMS = { "24": 1440, "6": 360, "1": 60 } as const;
type Zoom = keyof typeof ZOOMS;

const isoAt = (day: string, minute: number) => {
  const m = Math.max(0, Math.min(1439.9, minute));
  const h = Math.floor(m / 60);
  const mi = Math.floor(m % 60);
  const s = Math.floor((m * 60) % 60);
  return `${day}T${String(h).padStart(2, "0")}:${String(mi).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
};

function SearchPanel({ onPick }: { onPick: (h: SearchHit) => void }) {
  const [q, setQ] = useState("");
  const [days, setDays] = useState(7);
  const lightbox = useLightbox();
  const search = useMutation({ mutationFn: () => ext.search(q, days), onError: (e: Error) => toast.error(e.message) });
  function submit(e: FormEvent) {
    e.preventDefault();
    if (q.trim()) search.mutate();
  }
  const hits = search.data?.results ?? [];
  return (
    <Card>
      <CardHeader icon={<Search />} title="Arxivdan qidirish" description="Oddiy tilda yozing: «ombor eshigi qachon ochiq qoldi?», «kechasi avtoturargohda kim bo'lgan?»" />
      <CardBody>
        <form onSubmit={submit} className="flex flex-wrap gap-2">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nimani qidiramiz?" className="min-w-60 flex-1" aria-label="Qidiruv so'rovi" />
          <Select value={days} onChange={(e) => setDays(Number(e.target.value))} className="w-36" aria-label="Davr">
            <option value={1}>Bugun</option>
            <option value={3}>3 kun</option>
            <option value={7}>7 kun</option>
            <option value={30}>30 kun</option>
          </Select>
          <Button type="submit" variant="primary" loading={search.isPending} disabled={!q.trim()}>
            <Sparkles /> Qidirish
          </Button>
        </form>
        <AnimatePresence>
          {search.data ? (
            <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mt-4 space-y-3">
              <p className="rounded-xl border bg-surface-2 p-3 text-sm leading-relaxed">{search.data.answer}</p>
              {hits.length ? (
                <ul className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  {hits.map((h, i) => (
                    <motion.li key={`${h.ts}-${h.channel}`} initial={{ opacity: 0, scale: 0.95 }} animate={{ opacity: 1, scale: 1 }} transition={{ delay: i * 0.05 }} className="overflow-hidden rounded-xl border bg-surface">
                      {h.image ? (
                        <button className="block w-full" onClick={() => lightbox.open([h.image as string], 0, h.text)}>
                          <img src={h.image} alt="" loading="lazy" className="aspect-video w-full object-cover" />
                        </button>
                      ) : null}
                      <div className="space-y-1 p-2.5">
                        <p className="font-mono text-[10px] text-fg-subtle">{h.ts.replace("T", " ").slice(5, 16)} · {channelLabel(h.channel)}</p>
                        <p className="line-clamp-2 text-[11px] leading-snug">{h.text}</p>
                        <button onClick={() => onPick(h)} className="text-[11px] font-medium text-brand hover:underline">Shu lahzaga o'tish →</button>
                      </div>
                    </motion.li>
                  ))}
                </ul>
              ) : null}
            </motion.div>
          ) : null}
        </AnimatePresence>
      </CardBody>
    </Card>
  );
}

export function ArchivePage() {
  const [params, setParams] = useSearchParams();
  const config = useConfig();
  const cameras = config.data?.cameras ?? [];
  const channel = Number(params.get("channel") ?? 0) || config.data?.attendance_channels.at(-1) || 1;
  const day = params.get("day") ?? todayIso();
  const at = params.get("at");
  const [cursor, setCursor] = useState<number>(() => {
    if (at) return Number(at.slice(0, 2)) * 60 + Number(at.slice(3, 5));
    const n = new Date();
    return Math.max(0, n.getHours() * 60 + n.getMinutes() - 5);
  });
  const [zoom, setZoom] = useState<Zoom>(at ? "1" : "24");
  const { data, isLoading } = useTimeline(channel, day);
  const [frames, setFrames] = useState<string[] | null>(null);
  const [jobs, setJobs] = useState<JobInfo[]>([]);
  const allJobs = useJobs();
  const lightbox = useLightbox();

  const span = ZOOMS[zoom];
  const ws = Math.max(0, Math.min(1440 - span, cursor - span / 2));
  const win: [number, number] = [ws, ws + span];

  const set = (patch: Record<string, string | null>) =>
    setParams((p) => {
      const n = new URLSearchParams(p);
      for (const [k, v] of Object.entries(patch)) (v == null ? n.delete(k) : n.set(k, v));
      return n;
    }, { replace: true });

  const snaps = useMutation({
    mutationFn: () => api.archiveSnapshots(channel, isoAt(day, cursor), isoAt(day, cursor + 0.4), 4),
    onSuccess: (r) => {
      setFrames(r.frames_b64.map(b64Jpeg));
      if (!r.found) toast.warning("Bu lahzada arxivdan kadr olinmadi");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const clip = useMutation({
    mutationFn: () => ext.clipJob(channel, isoAt(day, cursor), 30),
    onSuccess: (j) => setJobs((s) => [j, ...s]),
    onError: (e: Error) => toast.error(e.message),
  });
  const summary = useMutation({
    mutationFn: (allCams: boolean) => ext.summaryJob(day, allCams ? null : channel),
    onSuccess: (j) => setJobs((s) => [j, ...s]),
    onError: (e: Error) => toast.error(e.message),
  });

  const isFuture = day === todayIso() && cursor > new Date().getHours() * 60 + new Date().getMinutes();
  const otherJobs = (allJobs.data ?? []).filter((j) => !jobs.some((x) => x.id === j.id)).slice(0, 6);

  return (
    <div className="flex flex-col gap-5">
      <SearchPanel
        onPick={(h) => {
          set({ channel: String(h.channel), day: h.ts.slice(0, 10), at: h.ts.slice(11, 16) });
          setCursor(Number(h.ts.slice(11, 13)) * 60 + Number(h.ts.slice(14, 16)));
          setZoom("1");
          window.scrollTo({ top: 300, behavior: "smooth" });
        }}
      />

      <Card>
        <CardHeader
          icon={<Film />}
          title="Kun chizig'i"
          description="Vaqtni bosing yoki sudrang (← → klavishlari ham ishlaydi), so'ng kadrlarni ko'ring yoki klip kesing"
          actions={
            <>
              <Select value={channel} onChange={(e) => set({ channel: e.target.value })} className="h-8 w-56" aria-label="Kamera">
                {cameras.map((c) => (
                  <option key={c.channel} value={c.channel}>{channelLabel(c.channel)} · {c.name}</option>
                ))}
              </Select>
              <div className="flex items-center gap-0.5 rounded-lg border bg-surface-2 p-0.5">
                <Button size="icon-sm" variant="ghost" aria-label="Oldingi kun" onClick={() => set({ day: shiftDate(day, -1) })}><ChevronLeft /></Button>
                <label className="relative flex items-center gap-1.5 px-1.5 text-xs font-medium">
                  <CalendarDays className="size-3.5 text-brand" /> {formatDayLong(day)}
                  <input type="date" value={day} max={todayIso()} onChange={(e) => e.target.value && set({ day: e.target.value })} className="absolute inset-0 cursor-pointer opacity-0" aria-label="Sana" />
                </label>
                <Button size="icon-sm" variant="ghost" aria-label="Keyingi kun" disabled={day >= todayIso()} onClick={() => set({ day: shiftDate(day, 1) })}><ChevronRight /></Button>
              </div>
              <Segmented ariaLabel="Masshtab" value={zoom} onChange={setZoom} options={[{ value: "24", label: "24 s" }, { value: "6", label: "6 s" }, { value: "1", label: "1 s", icon: <ZoomIn /> }]} />
            </>
          }
        />
        <CardBody className="space-y-4">
          {isLoading ? <Skeleton className="h-[140px]" /> : <Timeline data={data} window={win} cursor={cursor} onCursor={setCursor} />}
          <div className="flex flex-wrap items-center gap-3 text-[11px] text-fg-subtle">
            <span className="flex items-center gap-1.5"><span className="h-2 w-4 rounded-sm bg-fg-subtle/35" /> uzluksiz yozuv</span>
            <span className="flex items-center gap-1.5"><span className="h-2 w-4 rounded-sm bg-good/70" /> harakat yozuvi</span>
            <span className="flex items-center gap-1.5"><span className="h-3 w-2 rounded-sm" style={{ background: "var(--color-series-1)" }} /> harakat intensivligi</span>
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-good" /> xodim</span>
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-serious" /> notanish</span>
            <span className="flex items-center gap-1.5 text-critical">▲ ogohlantirish</span>
            {data ? <Badge className="ml-auto">{data.sightings.length} yuz · {data.alerts.length} ogohlantirish</Badge> : null}
          </div>
          <div className="flex flex-wrap items-center gap-2 border-t pt-4">
            <span className="mr-1 font-mono text-sm font-semibold tabular">{formatDayLong(day)} · {formatMinute(cursor)}</span>
            <Button size="sm" onClick={() => snaps.mutate()} loading={snaps.isPending} disabled={isFuture}><Images /> Kadrlarni ko'rish</Button>
            <Button size="sm" variant="primary" onClick={() => clip.mutate()} loading={clip.isPending} disabled={isFuture}><Clapperboard /> 30 s klip</Button>
            <div className="ml-auto flex gap-2">
              <Button size="sm" onClick={() => summary.mutate(false)} loading={summary.isPending}><Sparkles /> Bu kamera xulosasi</Button>
              <Button size="sm" onClick={() => summary.mutate(true)} loading={summary.isPending}><ListVideo /> Kunning video xulosasi</Button>
            </div>
          </div>
          <AnimatePresence>
            {frames ? (
              frames.length ? (
                <motion.ul initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="grid grid-cols-2 gap-3 md:grid-cols-4">
                  {frames.map((f, i) => (
                    <li key={f.slice(-20)}>
                      <button onClick={() => lightbox.open(frames, i)} className="block overflow-hidden rounded-xl border transition hover:border-brand">
                        <img src={f} alt={`Kadr ${i + 1}`} className="aspect-video w-full object-cover" />
                      </button>
                    </li>
                  ))}
                </motion.ul>
              ) : (
                <EmptyState icon={<Images />} title="Kadr topilmadi">Bu lahzada yozuv yo'q yoki kameralar ulanmagan.</EmptyState>
              )
            ) : null}
          </AnimatePresence>
        </CardBody>
      </Card>

      {jobs.length || otherJobs.length ? (
        <Card>
          <CardHeader icon={<Clapperboard />} title="Video vazifalar" description="Klip va xulosalar fonda tayyorlanadi — sahifani yopsangiz ham davom etadi" />
          <CardBody className="grid gap-4 md:grid-cols-2">
            {[...jobs, ...otherJobs].map((j) => <JobProgress key={j.id} initial={j} />)}
          </CardBody>
        </Card>
      ) : null}
    </div>
  );
}
