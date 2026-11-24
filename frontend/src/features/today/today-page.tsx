import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Briefcase, Clock3, MapPin, UserRoundCheck, UserRoundX, X } from "lucide-react";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";
import { Link } from "react-router";
import { StatTile } from "@/components/stat-tile";
import { Badge, StatusDot, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input } from "@/components/ui/field";
import { Avatar, EmptyState, Skeleton } from "@/components/ui/misc";
import { SEVERITY_STYLE } from "@/features/alerts/alert-meta";
import { ext } from "@/lib/api";
import { keys, useAlerts, useAttendance, useEmployees } from "@/lib/queries";
import type { AttendanceRow, TimeCategory } from "@/lib/types";
import { channelLabel, cn, formatMinutes, hhmm, todayIso } from "@/lib/utils";

function arrival(r: AttendanceRow): { tone: BadgeTone; text: string } {
  if (r.status === "kelmagan") return { tone: "critical", text: "Kelmagan" };
  const time = r.arrived ? hhmm(r.arrived) : "";
  if (r.late_minutes) return { tone: "warning", text: `${time} · ${r.late_minutes} daq kechikdi` };
  if (r.status === "ketgan" && r.left) return { tone: "neutral", text: `Ketdi ${hhmm(r.left)}` };
  return { tone: "good", text: `Keldi ${time}` };
}

const CONF = { seen: "ko'rildi", inferred: "taxmin", unknown: "kamera ko'rmayapti" } as const;
const TIME: [TimeCategory, string][] = [
  ["ish", "Ish xonasida"], ["majlis", "Majlisda"], ["safar", "Tashqarida ishda"], ["qoshimcha", "Qo'shimcha"],
  ["tushlik", "Tushlik"], ["tanaffus", "Tanaffus"], ["dam", "Dam olish xonasi"], ["tashqarida", "Ofisdan tashqarida"], ["nomalum", "Ma'lum emas"],
];

function Place({ row }: { row: AttendanceRow }) {
  const p = row.now_place;
  if (!p || row.status === "kelmagan") return <span className="text-xs text-fg-subtle">—</span>;
  const tone = p.conf === "unknown" || p.kind === "unknown" ? "neutral" : p.kind === "out" ? "critical" : p.conf === "seen" ? "good" : "warning";
  return (
    <span className="flex min-w-0 items-center gap-1.5 text-xs" title={`${CONF[p.conf]} · ${hhmm(p.since)} dan`}>
      <StatusDot tone={tone} /> <span className="truncate font-medium">{p.name}</span>
      <span className="shrink-0 text-fg-subtle">{CONF[p.conf]}</span>
    </span>
  );
}

function AwayForm({ row, onDone }: { row: AttendanceRow; onDone: () => void }) {
  const qc = useQueryClient();
  const now = new Date().toTimeString().slice(0, 5);
  const [form, setForm] = useState({ start: now, end: row.work_end > now ? row.work_end : "23:59", reason: "" });
  const save = useMutation({
    mutationFn: () => ext.addAway({ employee_id: row.id, ...form }),
    onSuccess: () => { void qc.invalidateQueries({ queryKey: keys.attendance(todayIso()) }); onDone(); },
    onError: (e: Error) => toast.error(e.message),
  });
  const submit = (e: FormEvent) => { e.preventDefault(); save.mutate(); };
  return (
    <form onSubmit={submit} className="flex flex-wrap items-center gap-2">
      <Input type="time" aria-label="Boshlanishi" value={form.start} onChange={(e) => setForm({ ...form, start: e.target.value })} className="h-8 w-28" required />
      <span className="text-fg-subtle">—</span>
      <Input type="time" aria-label="Tugashi" value={form.end} onChange={(e) => setForm({ ...form, end: e.target.value })} className="h-8 w-28" required />
      <Input aria-label="Sabab" placeholder="Sabab: mijoz, bank…" value={form.reason} onChange={(e) => setForm({ ...form, reason: e.target.value })} className="h-8 min-w-0 flex-1" />
      <Button type="submit" size="sm" variant="primary" loading={save.isPending}>Saqlash</Button>
      <Button size="sm" variant="ghost" onClick={onDone}>Bekor</Button>
    </form>
  );
}

function Details({ row }: { row: AttendanceRow }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const del = useMutation({ mutationFn: ext.deleteAway, onSuccess: () => void qc.invalidateQueries({ queryKey: keys.attendance(todayIso()) }) });
  const parts = TIME.filter(([k]) => row.time?.[k]);
  return (
    <div className="col-span-full flex flex-col gap-2 pl-[52px]">
      {parts.length ? (
        <p className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-fg-muted">
          {parts.map(([k, label]) => <span key={k}>{label} <b className="text-fg tabular">{formatMinutes(row.time![k])}</b></span>)}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-2">
        {row.away.map((a) => (
          <Badge key={a.id} tone="neutral">
            Tashqarida ishda {a.start}–{a.end}{a.reason ? ` · ${a.reason}` : ""}
            <button type="button" aria-label="O'chirish" onClick={() => del.mutate(a.id)} className="ml-1 opacity-70 hover:opacity-100"><X className="size-3" /></button>
          </Badge>
        ))}
        {open ? <AwayForm row={row} onDone={() => setOpen(false)} /> : (
          <button type="button" onClick={() => setOpen(true)} className="flex items-center gap-1 text-[11px] font-medium text-brand hover:underline">
            <Briefcase className="size-3" /> Tashqarida ishda deb belgilash
          </button>
        )}
      </div>
    </div>
  );
}

/** Xojayin sahifasi: kim keldi, kim joyida, nima bo'ldi. */
export function TodayPage() {
  const { data, isLoading } = useAttendance(todayIso());
  const employees = useEmployees();
  const alerts = useAlerts({ unacked: true });
  const rows = data?.employees ?? [];
  const rank = (r: AttendanceRow) => (r.status === "kelmagan" ? 0 : r.late_minutes ? 1 : 2);
  const sorted = [...rows].sort((a, b) => rank(a) - rank(b));
  const placed = rows.filter((r) => r.room && r.status !== "kelmagan");
  const events = (alerts.data?.items ?? []).filter((a) => a.kind !== "arrival" && a.kind !== "daily_summary").slice(0, 3);

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <StatTile index={0} loading={isLoading} icon={<UserRoundCheck />} tone="good" label="Keldi" value={data?.summary.present ?? 0} suffix={`/ ${data?.summary.total_employees ?? 0}`} />
        <StatTile index={1} loading={isLoading} icon={<Clock3 />} tone="warning" label="Kechikdi" value={data?.summary.late ?? 0} />
        <StatTile index={2} loading={isLoading} icon={<UserRoundX />} tone="critical" label="Kelmagan" value={rows.filter((r) => r.status === "kelmagan").length} />
        <StatTile index={3} loading={isLoading} icon={<MapPin />} tone="accent" label="Ish xonasida" value={placed.filter((r) => r.now_place?.name === r.room).length} suffix={`/ ${placed.length}`} />
      </div>

      <Card>
        <CardHeader icon={<UserRoundCheck />} title="Xodimlar" description="Kechikkan va kelmaganlar yuqorida" />
        <CardBody className="p-0">
          {isLoading ? (
            <div className="space-y-2 p-4">{Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-14" />)}</div>
          ) : !rows.length ? (
            <EmptyState icon={<UserRoundCheck />} title="Xodimlar qo'shilmagan">Xodimlarni admin qo'shadi.</EmptyState>
          ) : (
            <ul className="divide-y">
              {sorted.map((r) => {
                const a = arrival(r);
                return (
                  <li key={r.id} className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-3 gap-y-1 px-4 py-3 sm:grid-cols-[auto_minmax(0,1fr)_190px_200px_110px]">
                    <Avatar name={r.name} src={employees.data?.find((e) => e.id === r.id)?.avatar} />
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{r.name}</p>
                      <p className="truncate text-xs text-fg-muted">{r.position || "—"}</p>
                    </div>
                    <Badge tone={a.tone} className="justify-self-end sm:justify-self-start">{a.text}</Badge>
                    <div className="col-start-2 min-w-0 sm:col-start-auto"><Place row={r} /></div>
                    <p className="col-start-3 text-right text-xs tabular sm:col-start-auto">
                      {r.efficiency == null ? "—" : <><b>{formatMinutes(r.desk_minutes)}</b> <span className="text-fg-muted">· {r.efficiency}%</span></>}
                    </p>
                    <Details row={r} />
                  </li>
                );
              })}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader icon={<Clock3 />} title="Oxirgi hodisalar" actions={<Link to="/alerts" className="text-xs font-medium text-brand hover:underline">Barchasi →</Link>} />
        <CardBody className="p-0">
          {events.length ? (
            <ul className="divide-y">
              {events.map((e) => {
                const st = SEVERITY_STYLE[e.severity];
                return (
                  <li key={e.id} className="flex items-center gap-3 px-4 py-3">
                    <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg", st.soft)}><st.icon className="size-4" /></span>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{e.title}</p>
                      <p className="truncate text-xs text-fg-muted">{hhmm(e.ts)} · {e.kind_label}{e.channel ? ` · ${channelLabel(e.channel)}` : ""}</p>
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="px-4 py-8 text-center text-xs text-fg-subtle">Yangi hodisa yo'q</p>
          )}
        </CardBody>
      </Card>
    </div>
  );
}
