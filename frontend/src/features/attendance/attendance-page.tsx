import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3, Briefcase, CalendarDays, ChevronLeft, ChevronRight, Clock3, DoorOpen, ListFilter, LogOut,
  Monitor, ScanFace, Server, UserRoundCheck, UserRoundX, UsersRound,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { Link } from "react-router";
import { toast } from "sonner";
import { useLightbox } from "@/components/lightbox";
import { StatTile } from "@/components/stat-tile";
import { Badge, type BadgeTone, StatusDot } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Switch } from "@/components/ui/field";
import { Avatar, EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { api } from "@/lib/api";
import { keys, useAttendance, useEmployees, useWeekAttendance, useWorkers } from "@/lib/queries";
import type { AttendanceEvent, AttendanceRow, AttendanceStatus } from "@/lib/types";
import { channelLabel, cn, formatDayLong, formatMinutes, hhmm, parseWindow, shiftDate, todayIso } from "@/lib/utils";
import { DayTimeline } from "./day-timeline";
import { WeekChart } from "./week-chart";

const STATUS: Record<AttendanceStatus, { tone: BadgeTone; label: string }> = {
  ofisda: { tone: "good", label: "Ofisda" },
  ketgan: { tone: "neutral", label: "Ketgan" },
  kelmagan: { tone: "critical", label: "Kelmagan" },
  "chiqish qayd etilmagan": { tone: "warning", label: "Chiqish yo'q" },
};

function Efficiency({ value }: { value: number | null }) {
  if (value == null) return <span className="text-xs text-fg-subtle">kuzatilmagan</span>;
  const color = value >= 80 ? "var(--color-good)" : value >= 60 ? "var(--color-warning)" : "var(--color-critical)";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-3">
        <motion.div className="h-full rounded-full" style={{ background: color }} initial={{ width: 0 }} animate={{ width: `${Math.min(100, value)}%` }} transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }} />
      </div>
      <span className="w-9 text-right font-mono text-xs font-semibold tabular">{value}%</span>
    </div>
  );
}

function WorkerChips() {
  const { data: w } = useWorkers();
  const qc = useQueryClient();
  const force = useMutation({
    mutationFn: api.forceWorkers,
    onSuccess: (s) => {
      qc.setQueryData(keys.workers, s);
      toast.success(s.force_on ? "Kuzatuv hozir majburan yoqildi" : "Kuzatuv faqat ish vaqtida");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const desk = useMutation({
    mutationFn: api.deskCheckNow,
    onSuccess: (res) => {
      const items = Object.values(res).flat();
      if (items.length) toast.success(items.map((i) => `${i.name}: ${i.present ? "joyida" : "yo'q"}`).join(" · "));
      else toast.warning("Ish joyi biriktirilgan xodim yo'q yoki kamera javob bermadi");
      void qc.invalidateQueries({ queryKey: ["attendance"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!w) return <Skeleton className="h-10 w-full" />;
  type Tone = "good" | "warning" | "critical" | "neutral";
  const chips: { key: string; icon: typeof Server; tone: Tone; text: string }[] = [
    { key: "nvr", icon: Server, tone: w.nvr_online ? "good" : "critical", text: w.nvr_online ? "NVR ulangan" : "NVR ulanmagan" },
    {
      key: "face",
      icon: ScanFace,
      tone: w.face_engine.ready ? "good" : "warning",
      text: w.face_engine.ready ? `Yuz tanish · ${w.face_engine.employees} xodim / ${w.face_engine.samples} namuna` : "Yuz tanish tayyor emas",
    },
    {
      key: "win",
      icon: Clock3,
      tone: w.in_monitor_window || w.force_on ? "good" : "neutral",
      text: `Oyna ${w.monitor_window}${w.force_on ? " · majburiy" : w.in_monitor_window ? " · faol" : " · hozir emas"}`,
    },
    ...w.watchers.map((x) => ({
      key: `w${x.channel}`,
      icon: DoorOpen,
      tone: (x.connected ? "good" : "neutral") as Tone,
      text: `${channelLabel(x.channel)} · ${x.state}${x.sightings ? ` · ${x.sightings} ko'rinish` : ""}`,
    })),
    { key: "desk", icon: Monitor, tone: (w.desk.state === "faol" ? "good" : "neutral") as Tone, text: `Ish joylari · ${w.desk.state}${w.desk.last_check_at ? ` · ${hhmm(w.desk.last_check_at)}` : ""}` },
  ];

  return (
    <div className="flex flex-wrap items-center gap-2">
      {chips.map((c, i) => (
        <motion.span
          key={c.key}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: i * 0.04 }}
          className="inline-flex items-center gap-2 rounded-lg border bg-surface px-2.5 py-1.5 text-[11px] text-fg-muted"
        >
          <StatusDot tone={c.tone} pulse={c.tone === "good"} />
          <c.icon className="size-3.5" />
          {c.text}
        </motion.span>
      ))}
      <div className="ml-auto flex flex-wrap items-center gap-3">
        <Switch checked={w.force_on} onChange={(v) => force.mutate(v)} disabled={force.isPending} label={<span className="text-xs">Ish vaqtidan tashqari ham kuzatish</span>} />
        <Button size="sm" onClick={() => desk.mutate()} loading={desk.isPending}>
          <Monitor /> Ish joylarini tekshirish
        </Button>
      </div>
    </div>
  );
}

const METHOD_LABEL = { face: "yuzi tanildi", zone: "joyida odam bor", seat: "joyda harakat bor", room: "xonada odam bor" } as const;

/** Hozir kim o'z ish joyida — oxirgi tekshiruv natijasi. */
function WorkplaceBoard({ rows }: { rows: AttendanceRow[] }) {
  const { data: w } = useWorkers();
  const items = rows.filter((r) => r.workplace);
  if (!items.length) return null;
  return (
    <Card>
      <CardHeader icon={<Monitor />} title="Ish joylari — hozir" description="Har daqiqada tekshiriladi" />
      <CardBody className="grid gap-2 sm:grid-cols-2">
        {items.map((r) => {
          const now = w?.desk.now[String(r.id)];
          return (
            <div key={r.id} className="flex items-center gap-3 rounded-lg bg-surface-2 px-3 py-2">
              <span className={cn("size-2 shrink-0 rounded-full", now == null ? "bg-fg-subtle" : now.present ? "bg-good" : "bg-critical")} />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium">{r.name}</p>
                <p className="truncate text-xs text-fg-muted">
                  {channelLabel(r.workplace!.channel)} · {r.workplace!.camera} · {r.workplace!.mode === "zone" ? "joy" : "butun xona"}
                </p>
              </div>
              <div className="shrink-0 text-right text-xs">
                <p className="font-medium">{now == null ? "tekshirilmagan" : now.present ? "joyida" : "yo'q"}</p>
                {now ? <p className="text-fg-subtle">{now.present ? METHOD_LABEL[now.method] : ""} {now.at.slice(11, 16)}</p> : null}
              </div>
            </div>
          );
        })}
      </CardBody>
    </Card>
  );
}

function EmployeeRowCells({ row, win, live, avatar }: { row: AttendanceRow; win: [number, number]; live: boolean; avatar: string | null }) {
  const st = STATUS[row.status];
  return (
    <>
      <td className="py-3 pr-3">
        <div className="flex items-center gap-3">
          <Avatar name={row.name} src={avatar} size={36} />
          <div className="min-w-0">
            <p className="truncate font-medium">{row.name}</p>
            <p className="truncate text-[11px] text-fg-subtle">
              {row.position || "—"} · {row.work_start}–{row.work_end}
            </p>
          </div>
        </div>
      </td>
      <td className="px-3">
        <Badge tone={st.tone}>{st.label}</Badge>
      </td>
      <td className="px-3 font-mono text-xs tabular">
        {hhmm(row.arrived)}
        {row.arrived_approx ? <span title="Ish joyi kamerasidan taxminiy" className="text-fg-subtle">*</span> : null}
        {row.late_minutes ? <p className="text-[10px] text-[color-mix(in_oklab,var(--color-warning)_75%,var(--color-fg))]">+{row.late_minutes} daq</p> : null}
      </td>
      <td className="px-3 font-mono text-xs tabular">
        {hhmm(row.left)}
        {row.early_minutes ? <p className="text-[10px] text-critical">−{row.early_minutes} daq</p> : null}
      </td>
      <td className="px-3 text-xs">{formatMinutes(row.office_minutes)}</td>
      <td className="px-3 text-xs" title={row.efficiency == null ? undefined : `Yuz bilan tasdiqlangan: ${formatMinutes(row.confirmed_minutes)}`}>{row.efficiency == null ? "—" : formatMinutes(row.desk_minutes)}</td>
      <td className="px-3">
        <Efficiency value={row.efficiency} />
      </td>
      <td className="pl-3">
        <DayTimeline row={row} window={win} live={live} />
      </td>
    </>
  );
}

function EmployeeCard({ row, win, live, avatar }: { row: AttendanceRow; win: [number, number]; live: boolean; avatar: string | null }) {
  const st = STATUS[row.status];
  return (
    <div className="rounded-xl border bg-surface-2/50 p-3.5">
      <div className="flex items-center gap-3">
        <Avatar name={row.name} src={avatar} size={40} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">{row.name}</p>
          <p className="truncate text-[11px] text-fg-subtle">{row.position || "—"}</p>
        </div>
        <Badge tone={st.tone}>{st.label}</Badge>
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-center text-[11px]">
        {[
          ["Keldi", hhmm(row.arrived) + (row.late_minutes ? ` (+${row.late_minutes})` : "")],
          ["Ketdi", hhmm(row.left)],
          ["Ofisda", formatMinutes(row.office_minutes)],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg bg-surface px-2 py-1.5">
            <dt className="text-fg-subtle">{k}</dt>
            <dd className="mt-0.5 font-mono font-semibold tabular">{v}</dd>
          </div>
        ))}
      </dl>
      <div className="mt-3 flex items-center justify-between gap-3">
        <span className="text-[11px] text-fg-subtle">Ish joyida, %</span>
        <Efficiency value={row.efficiency} />
      </div>
      <div className="mt-3">
        <DayTimeline row={row} window={win} live={live} />
      </div>
    </div>
  );
}

const DIR_BADGE = {
  IN: { tone: "good", label: "Kirdi", icon: DoorOpen },
  OUT: { tone: "warning", label: "Chiqdi", icon: LogOut },
  UNKNOWN: { tone: "critical", label: "Notanish", icon: UserRoundX },
} as const;

function EventsFeed({ events }: { events: AttendanceEvent[] }) {
  const [filter, setFilter] = useState<"all" | "known" | "unknown">("all");
  const lightbox = useLightbox();
  const rows = events.filter((e) => filter === "all" || (filter === "known" ? e.employee_id != null : e.employee_id == null));
  return (
    <Card className="flex flex-col">
      <CardHeader
        icon={<ListFilter />}
        title="Kirish-chiqish lentasi"
        description={`${events.length} ta hodisa`}
        actions={
          <Segmented
            ariaLabel="Hodisalar filtri"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "Hammasi" },
              { value: "known", label: "Xodimlar" },
              { value: "unknown", label: "Notanish" },
            ]}
          />
        }
      />
      <CardBody className="max-h-[640px] overflow-y-auto">
        {rows.length ? (
          <ol className="relative space-y-2 before:absolute before:top-2 before:bottom-2 before:left-[27px] before:w-px before:bg-line">
            <AnimatePresence initial={false}>
              {rows.map((e) => {
                const d = DIR_BADGE[e.direction ?? "UNKNOWN"];
                return (
                  <motion.li
                    key={`${e.ts}-${e.channel}-${e.employee_id ?? e.sighting_id}`}
                    layout
                    initial={{ opacity: 0, x: -8 }}
                    animate={{ opacity: 1, x: 0 }}
                    exit={{ opacity: 0 }}
                    className="relative flex items-center gap-3 rounded-xl p-1.5 transition-colors hover:bg-surface-2"
                  >
                    <button
                      onClick={() => lightbox.open([e.frame_url], 0, `${e.name} · ${hhmm(e.ts)}`)}
                      className="relative shrink-0 overflow-hidden rounded-xl ring-2 ring-surface"
                      aria-label={`${e.name} kadrini ko'rish`}
                    >
                      <img src={e.face_url} alt="" loading="lazy" className="size-11 object-cover" />
                    </button>
                    <div className="min-w-0 flex-1">
                      <p className={cn("truncate text-sm font-medium", e.employee_id == null && "text-critical")}>{e.name}</p>
                      <p className="text-[11px] text-fg-subtle">{channelLabel(e.channel)}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <span className="font-mono text-xs font-semibold tabular">{hhmm(e.ts)}</span>
                      <Badge tone={d.tone} className="py-0">
                        <d.icon /> {d.label}
                      </Badge>
                    </div>
                  </motion.li>
                );
              })}
            </AnimatePresence>
          </ol>
        ) : (
          <EmptyState icon={<DoorOpen />} title="Hodisa yo'q">
            Kirish kameralari yuzlarni qayd etganda bu yerda paydo bo'ladi.
          </EmptyState>
        )}
      </CardBody>
    </Card>
  );
}

export function AttendancePage() {
  const [day, setDay] = useState(todayIso);
  const isToday = day === todayIso();
  const { data, isLoading, isFetching } = useAttendance(day);
  const week = useWeekAttendance(isToday ? day : todayIso());
  const workers = useWorkers();
  const employees = useEmployees();
  const win = parseWindow(workers.data?.monitor_window ?? "07:30–20:00");
  const avatars = useMemo(() => new Map((employees.data ?? []).map((e) => [e.id, e.avatar])), [employees.data]);
  const s = data?.summary;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-1 rounded-xl border bg-surface p-1 shadow-card">
          <Button size="icon-sm" variant="ghost" aria-label="Oldingi kun" onClick={() => setDay((d) => shiftDate(d, -1))}>
            <ChevronLeft />
          </Button>
          <label className="relative flex items-center gap-2 px-2">
            <CalendarDays className="size-4 text-brand" />
            <span className="text-sm font-medium">{formatDayLong(day)}</span>
            <Input
              type="date"
              value={day}
              max={todayIso()}
              onChange={(e) => e.target.value && setDay(e.target.value)}
              className="absolute inset-0 h-full cursor-pointer opacity-0"
              aria-label="Sanani tanlash"
            />
          </label>
          <Button size="icon-sm" variant="ghost" aria-label="Keyingi kun" disabled={isToday} onClick={() => setDay((d) => shiftDate(d, 1))}>
            <ChevronRight />
          </Button>
        </div>
        {isToday ? null : (
          <Button size="sm" variant="ghost" onClick={() => setDay(todayIso())}>
            Bugunga qaytish
          </Button>
        )}
        {isFetching && !isLoading ? <span className="text-xs text-fg-subtle">yangilanmoqda…</span> : null}
      </div>

      <WorkerChips />

      {isToday && data ? <WorkplaceBoard rows={data.employees} /> : null}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <StatTile index={0} loading={isLoading} icon={<UserRoundCheck />} tone="good" label="Kelganlar" value={s?.present ?? 0} suffix={`/ ${s?.total_employees ?? 0}`} hint={`${(s?.total_employees ?? 0) - (s?.present ?? 0)} kishi kelmagan`} />
        <StatTile index={1} loading={isLoading} icon={<Clock3 />} tone="warning" label="Kechikkanlar" value={s?.late ?? 0} />
        <StatTile index={2} loading={isLoading} icon={<LogOut />} tone="critical" label="Erta ketganlar" value={s?.early_leave ?? 0} />
        <StatTile index={3} loading={isLoading} icon={<Briefcase />} tone="brand" label="Jami ofis vaqti" value={s?.total_office_hours ?? 0} decimals={1} suffix="soat" />
        <StatTile index={4} loading={isLoading} icon={<UserRoundX />} tone="accent" label="Notanish yuzlar" value={s?.unknown_faces ?? 0} hint={<Link to="/employees" className="hover:text-brand">Biriktirish →</Link>} />
      </div>

      <div className="grid gap-5 2xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="flex min-w-0 flex-col gap-5">
          <Card>
            <CardHeader icon={<BarChart3 />} title="Oxirgi 7 kun — kelgan xodimlar" description="Ustunni bosing — o'sha kun ochiladi" />
            <CardBody>
              {week.isLoading ? <Skeleton className="h-[168px]" /> : <WeekChart days={week.days} reports={week.reports} selected={day} onSelect={setDay} />}
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              icon={<UsersRound />}
              title="Xodimlar"
              description={isToday ? "Bugungi holat · har 20 soniyada yangilanadi" : formatDayLong(day)}
              actions={
                <div className="hidden items-center gap-3 text-[10px] text-fg-subtle md:flex">
                  <span className="flex items-center gap-1.5"><span className="h-2 w-3 rounded-sm" style={{ background: "color-mix(in oklab, var(--color-series-1) 55%, transparent)" }} /> ofisda</span>
                  <span className="flex items-center gap-1.5"><span className="h-3 w-[3px] rounded-full" style={{ background: "var(--color-series-3)" }} /> stolda</span>
                  <span className="flex items-center gap-1.5"><span className="h-3 w-[3px] rounded-full bg-fg-subtle opacity-50" /> ish joyida yo'q</span>
                  <span className="flex items-center gap-1 text-good">▼ kirdi</span>
                  <span className="flex items-center gap-1" style={{ color: "var(--color-serious)" }}>▲ chiqdi</span>
                </div>
              }
            />
            <CardBody>
              {isLoading ? (
                <div className="space-y-2">
                  {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-14" />)}
                </div>
              ) : !data?.employees.length ? (
                <EmptyState icon={<UsersRound />} title="Hali xodim qo'shilmagan" action={<Link to="/employees"><Button variant="primary" size="sm">Xodim qo'shish</Button></Link>}>
                  Davomat yuritish uchun avval xodimlarni qo'shing va yuzlarini o'rgating.
                </EmptyState>
              ) : (
                <>
                  <div className="hidden overflow-x-auto lg:block">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-[11px] tracking-wide text-fg-subtle uppercase">
                          <th className="pb-2.5 pr-3 font-medium">Xodim</th>
                          <th className="px-3 pb-2.5 font-medium">Holat</th>
                          <th className="px-3 pb-2.5 font-medium">Keldi</th>
                          <th className="px-3 pb-2.5 font-medium">Ketdi</th>
                          <th className="px-3 pb-2.5 font-medium">Ofisda</th>
                          <th className="px-3 pb-2.5 font-medium">Ish joyida</th>
                          <th className="px-3 pb-2.5 font-medium">Ish joyida, %</th>
                          <th className="pb-2.5 pl-3 font-medium">Kun chizig'i</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {data.employees.map((row, i) => (
                          <motion.tr key={row.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.03 }} className="transition-colors hover:bg-surface-2/60">
                            <EmployeeRowCells row={row} win={win} live={isToday} avatar={avatars.get(row.id) ?? null} />
                          </motion.tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 lg:hidden">
                    {data.employees.map((row) => (
                      <EmployeeCard key={row.id} row={row} win={win} live={isToday} avatar={avatars.get(row.id) ?? null} />
                    ))}
                  </div>
                </>
              )}
            </CardBody>
          </Card>
        </div>
        <EventsFeed events={data?.events ?? []} />
      </div>
    </div>
  );
}
