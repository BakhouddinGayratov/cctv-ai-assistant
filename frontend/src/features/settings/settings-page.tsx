import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot, BrainCircuit, Database, FileBarChart, Send, ServerCog, ShieldAlert, Sparkles,
} from "lucide-react";
import { motion } from "motion/react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";
import { Badge, StatusDot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Switch } from "@/components/ui/field";
import { OfficeMapCard } from "./office-map";
import { Skeleton } from "@/components/ui/misc";
import { ext } from "@/lib/api";
import { extKeys, useConfig, useSettings, useSystem } from "@/lib/queries";
import type { AppSettings } from "@/lib/types";
import { channelLabel, cn } from "@/lib/utils";

function useSave() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: Partial<AppSettings>) => ext.saveSettings(body),
    onSuccess: (s) => {
      qc.setQueryData(extKeys.settings, s);
      toast.success("Saqlandi", { duration: 1500 });
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

function CameraPicker({ value, onChange, label }: { value: number[]; onChange: (v: number[]) => void; label: string }) {
  const { data } = useConfig();
  const set = new Set(value);
  return (
    <div>
      <p className="mb-2 text-xs font-medium text-fg-muted">{label}</p>
      <div className="flex flex-wrap gap-1.5">
        {(data?.cameras ?? []).map((c) => {
          const on = set.has(c.channel);
          return (
            <button
              key={c.channel}
              type="button"
              title={c.name}
              aria-pressed={on}
              onClick={() => onChange(on ? value.filter((x) => x !== c.channel) : [...value, c.channel].sort((a, b) => a - b))}
              className={cn(
                "rounded-lg border px-2.5 py-1 font-mono text-[11px] transition",
                on ? "border-brand bg-brand-soft text-brand" : "text-fg-muted hover:border-line-strong",
              )}
            >
              {channelLabel(c.channel)}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Row({ title, hint, control }: { title: ReactNode; hint?: ReactNode; control: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0">
      <div className="min-w-0">
        <p className="text-sm font-medium">{title}</p>
        {hint ? <p className="mt-0.5 text-xs text-fg-subtle">{hint}</p> : null}
      </div>
      {control}
    </div>
  );
}

function NumberInput({ value, onCommit, min = 1, max = 1440, suffix }: { value: number; onCommit: (v: number) => void; min?: number; max?: number; suffix?: string }) {
  const [v, setV] = useState(String(value));
  return (
    <div className="flex items-center gap-1.5">
      <Input
        type="number"
        min={min}
        max={max}
        value={v}
        onChange={(e) => setV(e.target.value)}
        onBlur={() => {
          const n = Math.min(max, Math.max(min, Number(v) || min));
          setV(String(n));
          if (n !== value) onCommit(n);
        }}
        className="h-8 w-20"
      />
      {suffix ? <span className="text-xs text-fg-subtle">{suffix}</span> : null}
    </div>
  );
}

function TimeInput({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  return <Input type="time" defaultValue={value} onBlur={(e) => e.target.value !== value && onCommit(e.target.value)} className="h-8 w-28" />;
}

export function SettingsPage() {
  const { data: s, isLoading } = useSettings();
  const save = useSave();
  const system = useSystem();
  const index = useQuery({ queryKey: ["index-stats"], queryFn: ext.indexStats, refetchInterval: 30_000 });
  const daily = useMutation({
    mutationFn: () => ext.dailySummary(),
    onSuccess: (a) => toast.success("Kunlik xulosa tayyor", { description: a.message.slice(0, 300), duration: 12_000 }),
    onError: (e: Error) => toast.error(e.message),
  });
  const weekly = useMutation({
    mutationFn: ext.weeklyReport,
    onSuccess: (r) => toast.success(`Haftalik hisobot: ${r.from} — ${r.to}`, { description: "Telegram ulangan bo'lsa yuborildi" }),
    onError: (e: Error) => toast.error(e.message),
  });
  const agent = useMutation({
    mutationFn: ext.runAgent,
    onSuccess: (r) => toast.info(r.messages.length ? r.messages.join("\n") : "Agent: hozircha e'tiborga loyiq holat yo'q"),
  });
  const runIndex = useMutation({
    mutationFn: ext.runIndex,
    onSuccess: (r) => {
      toast.success(`${r.written} ta kadr indekslandi`);
      void index.refetch();
    },
  });

  if (isLoading || !s) return <div className="grid gap-5 lg:grid-cols-2">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-64" />)}</div>;
  const set = (patch: Partial<AppSettings>) => save.mutate(patch);

  return (
    <motion.div className="grid gap-5 lg:grid-cols-2" initial="h" animate="s" variants={{ s: { transition: { staggerChildren: 0.05 } } }}>
      {[
        <Card key="alerts">
          <CardHeader icon={<ShieldAlert />} title="Ogohlantirishlar" description="Qaysi hodisalar haqida xabar berilsin" />
          <CardBody className="divide-y">
            <Row title="Notanish odam" hint="Kirish kamerasi tanimagan yuz — faqat saytda, Telegramga yuborilmaydi"
              control={<div className="flex items-center gap-3"><NumberInput value={s.alert_unknown_cooldown_min} onCommit={(v) => set({ alert_unknown_cooldown_min: v })} max={240} suffix="daq oraliq" /><Switch checked={s.alert_unknown_face} onChange={(v) => set({ alert_unknown_face: v })} label="" /></div>} />
            <Row title="Kamera aloqasi uzilsa" hint="3 daqiqadan ortiq oqim bo'lmasa"
              control={<Switch checked={s.alert_camera_offline} onChange={(v) => set({ alert_camera_offline: v })} label="" />} />
            <div className="space-y-3 py-3">
              <Row title="Ish vaqtidan tashqari harakat" hint="Harakat → YOLO odam/mashina tasdig'i → rasm + 10 s klip"
                control={<Switch checked={s.alert_after_hours} onChange={(v) => set({ alert_after_hours: v })} label="" />} />
              <div className="flex flex-wrap items-center gap-3 text-xs text-fg-muted">
                Qo'riqlash: <TimeInput value={s.after_hours_start} onCommit={(v) => set({ after_hours_start: v })} /> dan
                <TimeInput value={s.after_hours_end} onCommit={(v) => set({ after_hours_end: v })} /> gacha
                <Switch checked={s.after_hours_weekends} onChange={(v) => set({ after_hours_weekends: v })} label={<span className="text-xs">dam olish kunlari kun bo'yi</span>} />
              </div>
              <CameraPicker label="Qo'riqlanadigan kameralar" value={s.security_cameras} onChange={(v) => set({ security_cameras: v })} />
            </div>
          </CardBody>
        </Card>,

        <Card key="reports">
          <CardHeader icon={<FileBarChart />} title="Avtomatik hisobotlar" description="Kunlik AI xulosa va haftalik Excel/PDF" />
          <CardBody className="divide-y">
            <Row title="Kunlik AI xulosa" hint="Chatga va Telegram'ga yuboriladi"
              control={<div className="flex items-center gap-3"><TimeInput value={s.daily_summary_time} onCommit={(v) => set({ daily_summary_time: v })} /><Switch checked={s.daily_summary} onChange={(v) => set({ daily_summary: v })} label="" /></div>} />
            <Row title="Haftalik hisobot" hint="Har dushanba 08:00 — o'tgan hafta Excel + PDF Telegram'ga"
              control={<Switch checked={s.weekly_report} onChange={(v) => set({ weekly_report: v })} label="" />} />
            <div className="flex flex-wrap gap-2 pt-3">
              <Button size="sm" onClick={() => daily.mutate()} loading={daily.isPending}><Sparkles /> Bugungi xulosani hozir yaratish</Button>
              <Button size="sm" onClick={() => weekly.mutate()} loading={weekly.isPending}><Send /> Haftalik hisobotni yuborish</Button>
            </div>
          </CardBody>
        </Card>,

        <Card key="agent">
          <CardHeader icon={<Bot />} title="AI agent" description="Har 10 daqiqada holatni tekshirib, o'zi xabar beradi" />
          <CardBody className="divide-y">
            <Row title="Agent yoqilgan" control={<Switch checked={s.agent_enabled} onChange={(v) => set({ agent_enabled: v })} label="" />} />
            <Row title="Ish joyidan uzoqlashish chegarasi" hint="Ofisda bo'lib, shuncha vaqt ish joyida bo'lmasa xabar"
              control={<NumberInput value={s.agent_away_minutes} onCommit={(v) => set({ agent_away_minutes: v })} min={10} max={240} suffix="daq" />} />
            <Row title="Xodim kelganini Telegram'ga yuborish" hint="Kechikkan bo'lsa daqiqasi bilan"
              control={<Switch checked={s.announce_arrivals} onChange={(v) => set({ announce_arrivals: v })} label="" />} />
            <div className="pt-3"><Button size="sm" onClick={() => agent.mutate()} loading={agent.isPending}><Bot /> Hozir tekshirish</Button></div>
          </CardBody>
        </Card>,

        <Card key="presence">
          <CardHeader icon={<Bot />} title="Xodim qayerda" description="Tushlik vaqti va kamerasiz joylar chegaralari" />
          <CardBody className="divide-y">
            <Row title="Tushlik" hint="Bu vaqtda oshxona yoki ofisdan tashqari — yo'qlik emas"
              control={<div className="flex items-center gap-2 text-xs"><TimeInput value={s.lunch_start} onCommit={(v) => set({ lunch_start: v })} /> — <TimeInput value={s.lunch_end} onCommit={(v) => set({ lunch_end: v })} /></div>} />
            <Row title="Hovlida qisqa chiqish" hint="Shundan ko'p bo'lsa — ofisdan tashqarida"
              control={<NumberInput value={s.yard_max_min} onCommit={(v) => set({ yard_max_min: v })} min={1} max={120} suffix="daq" />} />
            <Row title="Kamerasiz joy chegarasi" hint="Shundan ko'p ko'rinmasa — rahbarga xabar"
              control={<NumberInput value={s.blind_max_min} onCommit={(v) => set({ blind_max_min: v })} min={1} max={240} suffix="daq" />} />
            <Row title="Kamerali xona bo'shasa" hint="Shuncha vaqt odam ko'rinmasa — joyi noma'lum"
              control={<NumberInput value={s.room_grace_min} onCommit={(v) => set({ room_grace_min: v })} min={1} max={60} suffix="daq" />} />
          </CardBody>
        </Card>,

        <OfficeMapCard key="map" />,

        <Card key="index">
          <CardHeader icon={<Database />} title="Semantik qidiruv indeksi" description="Kameralar kadrlari AI bilan tavsiflanadi — «ombor eshigi qachon ochiq qoldi?» kabi savollar uchun"
            actions={<Badge>{index.data?.frames ?? 0} kadr</Badge>} />
          <CardBody className="divide-y">
            <Row title="Indeksatsiya" hint={index.data?.last ? `Oxirgi: ${index.data.last.replace("T", " ")}` : "Hali indekslanmagan"}
              control={<Switch checked={s.indexer_enabled} onChange={(v) => set({ indexer_enabled: v })} label="" />} />
            <Row title="Oraliq" hint="17 kamera = har safar 2 ta AI so'rovi"
              control={<NumberInput value={s.indexer_interval_min} onCommit={(v) => set({ indexer_interval_min: v })} min={5} max={240} suffix="daq" />} />
            <div className="pt-3"><Button size="sm" onClick={() => runIndex.mutate()} loading={runIndex.isPending}><BrainCircuit /> Hozir indekslash</Button></div>
          </CardBody>
        </Card>,

        <Card key="system" className="lg:col-span-2">
          <CardHeader icon={<ServerCog />} title="Tizim holati" description={system.data?.security.after_hours_now ? "Hozir qo'riqlash rejimi (ish vaqtidan tashqari)" : "Hozir ish vaqti"} />
          <CardBody className="grid gap-5 md:grid-cols-2">
            <div>
              <p className="mb-2 text-xs font-medium text-fg-muted">Xavfsizlik kuzatuvchilari</p>
              <ul className="space-y-1.5">
                {(system.data?.security.watchers ?? []).map((w) => (
                  <li key={w.channel} className="flex items-center gap-2 rounded-lg bg-surface-2 px-3 py-2 text-xs">
                    <StatusDot tone={w.connected ? "good" : "neutral"} pulse={w.connected} />
                    <span className="font-mono">{channelLabel(w.channel)}</span>
                    <span className="text-fg-muted">{w.state}</span>
                    <span className="ml-auto font-mono text-fg-subtle tabular">harakat {Math.round(w.motion * 1000) / 10}%</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <p className="mb-2 text-xs font-medium text-fg-muted">Rejalashtirilgan vazifalar</p>
              <ul className="space-y-1.5 text-xs">
                {(system.data?.scheduler ?? []).map((j) => (
                  <li key={j.id} className="flex justify-between rounded-lg bg-surface-2 px-3 py-2">
                    <span>{{ daily: "Kunlik xulosa", weekly: "Haftalik hisobot", agent: "AI agent", index: "Semantik indeks", cleanup: "Tozalash" }[j.id] ?? j.id}</span>
                    <span className="font-mono text-fg-muted">{j.next_run?.replace("T", " ").slice(5, 16) ?? "—"}</span>
                  </li>
                ))}
              </ul>
            </div>
          </CardBody>
        </Card>,
      ].map((el, i) => (
        <motion.div key={i} variants={{ h: { opacity: 0, y: 14 }, s: { opacity: 1, y: 0 } }} className={i === 4 || i === 6 ? "lg:col-span-2" : undefined}>
          {el}
        </motion.div>
      ))}
    </motion.div>
  );
}
