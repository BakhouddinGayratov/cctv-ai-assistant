import { useQuery } from "@tanstack/react-query";
import {
  Activity, BarChart3, Briefcase, CalendarCheck2, Clock3, FileSpreadsheet, FileText, Flame, Gauge, Trophy, UserRoundX,
} from "lucide-react";
import { useMemo, useState } from "react";
import { BarList, ColumnChart } from "@/components/charts";
import { StatTile } from "@/components/stat-tile";
import { Badge } from "@/components/ui/badge";
import { buttonVariants } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { ext } from "@/lib/api";
import { useRole } from "@/lib/auth";
import { useAnalytics, useConfig } from "@/lib/queries";
import { channelLabel, cn, formatDayLong, shiftDate, todayIso, weekdayShort } from "@/lib/utils";

type Range = "7" | "30" | "month" | "custom";

function HeatmapCard({ day }: { day: string }) {
  const config = useConfig();
  const chans = useQuery({ queryKey: ["heat-ch", day], queryFn: () => ext.heatmapChannels(day) });
  const available = chans.data?.channels ?? [];
  const [ch, setCh] = useState<number | null>(null);
  const channel = ch ?? available[0] ?? null;
  const [failed, setFailed] = useState(false);
  return (
    <Card>
      <CardHeader
        icon={<Flame />}
        title="Issiqlik xaritasi"
        description="Kun davomida kadrning qaysi qismida ko'p harakat bo'lgan (kuzatiladigan kameralar)"
        actions={
          <Select value={channel ?? ""} onChange={(e) => { setCh(Number(e.target.value)); setFailed(false); }} className="h-8 w-56" aria-label="Kamera">
            {available.length ? null : <option value="">Ma'lumot yo'q</option>}
            {available.map((c) => (
              <option key={c} value={c}>
                {channelLabel(c)} · {config.data?.cameras.find((x) => x.channel === c)?.name}
              </option>
            ))}
          </Select>
        }
      />
      <CardBody>
        {channel != null && !failed ? (
          <div className="overflow-hidden rounded-xl border bg-black">
            <img src={ext.heatmapUrl(channel, day)} alt={`${channelLabel(channel)} issiqlik xaritasi`} onError={() => setFailed(true)} className="aspect-video w-full object-contain" />
            <div className="flex items-center gap-2 bg-surface px-3 py-2 text-[11px] text-fg-subtle">
              kam
              <span className="h-2 flex-1 rounded-full" style={{ background: "linear-gradient(90deg,#30123b,#4686fb,#1ae4b6,#a2fc3c,#fabb39,#e4460a,#7a0403)" }} />
              ko'p
            </div>
          </div>
        ) : (
          <EmptyState icon={<Flame />} title="Issiqlik xaritasi yo'q">
            {formatDayLong(day)} uchun faollik yozilmagan. Kuzatuv kameralari NVR'ga ulanganda avtomatik to'planadi.
          </EmptyState>
        )}
      </CardBody>
    </Card>
  );
}

export function AnalyticsPage() {
  const admin = useRole() === "admin";
  const [range, setRange] = useState<Range>("7");
  const today = todayIso();
  const [custom, setCustom] = useState({ from: shiftDate(today, -13), to: today });
  const from = range === "7" ? shiftDate(today, -6) : range === "30" ? shiftDate(today, -29) : range === "month" ? `${today.slice(0, 8)}01` : custom.from;
  const to = range === "custom" ? custom.to : today;
  const { data, isLoading, isFetching } = useAnalytics(from, to);
  const [heatDay, setHeatDay] = useState(today);

  const t = data?.totals;
  const many = (data?.days.length ?? 0) > 14;
  const dayCols = useMemo(
    () =>
      (data?.days ?? []).map((d) => ({
        key: d.date,
        label: many ? d.date.slice(8) : weekdayShort(d.date),
        value: d.present,
        muted: !d.workday,
        tooltip: (
          <>
            <b className="block text-fg">{formatDayLong(d.date)}</b>
            <span className="flex justify-between text-fg-muted">Kelgan <b className="text-fg">{d.present}/{d.total_employees}</b></span>
            <span className="flex justify-between text-fg-muted">Kechikkan <b className="text-fg">{d.late}</b></span>
            <span className="flex justify-between text-fg-muted">Ofis vaqti <b className="text-fg">{d.total_office_hours} s</b></span>
          </>
        ),
      })),
    [data, many],
  );
  const effCols = useMemo(
    () => (data?.days ?? []).map((d) => ({ key: d.date, label: many ? d.date.slice(8) : weekdayShort(d.date), value: d.avg_efficiency ?? 0, muted: d.avg_efficiency == null })),
    [data, many],
  );

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <Segmented
          ariaLabel="Davr"
          value={range}
          onChange={setRange}
          options={[
            { value: "7", label: "7 kun" },
            { value: "30", label: "30 kun" },
            { value: "month", label: "Bu oy" },
            { value: "custom", label: "Oraliq" },
          ]}
        />
        {range === "custom" ? (
          <div className="flex items-center gap-2">
            <Input type="date" value={custom.from} max={custom.to} onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value }))} className="h-8 w-40" aria-label="Boshlanish" />
            <span className="text-fg-subtle">—</span>
            <Input type="date" value={custom.to} max={today} onChange={(e) => setCustom((c) => ({ ...c, to: e.target.value }))} className="h-8 w-40" aria-label="Tugash" />
          </div>
        ) : null}
        <span className="text-xs text-fg-subtle">{from} — {to}{isFetching ? " · yangilanmoqda…" : ""}</span>
        <div className="ml-auto flex gap-2">
          <a href={ext.reportUrl("xlsx", from, to)} className={buttonVariants({ size: "sm" })} download>
            <FileSpreadsheet /> Excel
          </a>
          <a href={ext.reportUrl("pdf", from, to)} className={buttonVariants({ size: "sm", variant: "primary" })} download>
            <FileText /> PDF hisobot
          </a>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
        <StatTile index={0} loading={isLoading} icon={<Gauge />} tone="good" label="Davomat darajasi" value={t?.attendance_rate ?? 0} suffix="%" hint="ish kunlari bo'yicha" />
        <StatTile index={1} loading={isLoading} icon={<CalendarCheck2 />} tone="accent" label="Ish kunlari" value={t?.workdays ?? 0} />
        <StatTile index={2} loading={isLoading} icon={<Clock3 />} tone="warning" label="Kechikishlar" value={t?.late_total ?? 0} />
        <StatTile index={3} loading={isLoading} icon={<Briefcase />} tone="brand" label="Jami ofis vaqti" value={t?.office_hours ?? 0} decimals={1} suffix="soat" />
        <StatTile index={4} loading={isLoading} icon={<UserRoundX />} tone="critical" label="Notanish yuzlar" value={t?.unknown_faces ?? 0} />
      </div>

      <div className="grid gap-5 xl:grid-cols-2">
        <Card>
          <CardHeader icon={<BarChart3 />} title="Kunlik davomat" description="Kelgan xodimlar soni · xira — dam olish kuni" />
          <CardBody>{isLoading ? <Skeleton className="h-[180px]" /> : <ColumnChart data={dayCols} caption="Kunlik kelgan xodimlar" labelEvery={many ? 3 : 1} />}</CardBody>
        </Card>
        <Card>
          <CardHeader icon={<Gauge />} title="Ish joyida, %" description="Ish joyida o'tgan vaqt / ofisdagi vaqt, %" />
          <CardBody>{isLoading ? <Skeleton className="h-[180px]" /> : <ColumnChart data={effCols} caption="Kunlik o'rtacha ish joyida, %" color="var(--color-series-3)" labelEvery={many ? 3 : 1} />}</CardBody>
        </Card>

        <Card>
          <CardHeader icon={<Trophy />} title="Xodimlar reytingi" description="Ofisda o'tkazilgan vaqt (soat) · effektivlik · kechikishlar" />
          <CardBody>
            {data?.employees.length ? (
              <BarList
                unit=" s"
                items={data.employees.map((e) => ({
                  key: String(e.id),
                  label: e.name,
                  value: e.office_hours,
                  sub: (
                    <>
                      {e.avg_efficiency != null ? `${e.avg_efficiency}% · ` : ""}
                      {e.late_days ? <span className="text-[color-mix(in_oklab,var(--color-warning)_75%,var(--color-fg))]">{e.late_days} kechikish</span> : "kechikishsiz"}
                    </>
                  ),
                }))}
              />
            ) : (
              <EmptyState icon={<Trophy />} title="Ma'lumot yo'q">Davomat yozuvlari to'planganda reyting paydo bo'ladi.</EmptyState>
            )}
          </CardBody>
        </Card>

        {admin ? <><Card>
          <CardHeader icon={<Clock3 />} title="Kelish vaqtlari" description="Xodimlar soat nechada keladi (barcha kunlar)" />
          <CardBody>
            {isLoading ? <Skeleton className="h-[180px]" /> : (
              <ColumnChart caption="Kelish vaqtlari taqsimoti" color="var(--color-series-3)"
                data={(data?.arrival_histogram ?? []).map((h) => ({ key: String(h.hour), label: `${String(h.hour).padStart(2, "0")}:00`, value: h.count }))} />
            )}
            {data?.employees.some((e) => e.avg_arrival) ? (
              <ul className="mt-4 grid grid-cols-2 gap-2 text-xs sm:grid-cols-3">
                {data.employees.filter((e) => e.avg_arrival).map((e) => (
                  <li key={e.id} className="flex justify-between rounded-lg bg-surface-2 px-2.5 py-1.5">
                    <span className="truncate">{e.name}</span>
                    <span className="font-mono tabular">{e.avg_arrival}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </CardBody>
        </Card>

        <Card>
          <CardHeader icon={<Activity />} title="Soatlik faollik" description="Kameralarda harakat bo'lgan daqiqalar (kun soatlari bo'yicha)" />
          <CardBody>
            {isLoading ? <Skeleton className="h-[180px]" /> : (
              <ColumnChart caption="Soatlik faollik" labelEvery={3}
                data={(data?.hourly_activity ?? []).map((h) => ({ key: String(h.hour), label: String(h.hour).padStart(2, "0"), value: h.minutes }))} />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader icon={<BarChart3 />} title="Kameralar faolligi" description="Yuz ko'rinishlari va faol daqiqalar" />
          <CardBody>
            {data?.cameras.length ? (
              <table className="w-full text-xs">
                <thead className="text-left text-[11px] text-fg-subtle uppercase">
                  <tr className="border-b"><th className="pb-2 font-medium">Kamera</th><th className="pb-2 text-right font-medium">Yuzlar</th><th className="pb-2 text-right font-medium">Faol daq</th></tr>
                </thead>
                <tbody className="divide-y">
                  {data.cameras.map((c) => (
                    <tr key={c.channel}>
                      <td className="py-2"><span className="font-mono text-fg-subtle">{channelLabel(c.channel)}</span> {c.name}</td>
                      <td className="py-2 text-right font-mono tabular">{c.sightings}</td>
                      <td className="py-2 text-right font-mono tabular">{c.active_minutes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <EmptyState icon={<Activity />} title="Faollik yozilmagan">NVR ulanganda kuzatiladigan kameralar faolligi shu yerda chiqadi.</EmptyState>
            )}
            {data && Object.keys(data.alerts).length ? (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {Object.entries(data.alerts).map(([k, n]) => <Badge key={k}>{k}: {n}</Badge>)}
              </div>
            ) : null}
          </CardBody>
        </Card></> : null}
      </div>

      {admin ? <><div className="flex items-center gap-2">
        <span className="text-xs text-fg-muted">Issiqlik xaritasi sanasi:</span>
        <Input type="date" value={heatDay} max={today} onChange={(e) => e.target.value && setHeatDay(e.target.value)} className={cn("h-8 w-40")} />
      </div>
      <HeatmapCard key={heatDay} day={heatDay} /></> : null}
    </div>
  );
}
