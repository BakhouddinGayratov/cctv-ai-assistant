import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, CheckCheck, FlaskConical, ShieldCheck } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useMemo, useState } from "react";
import { toast } from "sonner";
import { useLightbox } from "@/components/lightbox";
import { Markdown } from "@/features/chat/markdown";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody } from "@/components/ui/card";
import { Input, Switch } from "@/components/ui/field";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { ext } from "@/lib/api";
import { useAlerts } from "@/lib/queries";
import type { AlertItem, AlertKind } from "@/lib/types";
import { channelLabel, cn, formatDayLong, hhmm, shiftDate, todayIso } from "@/lib/utils";
import { KIND_META, SEVERITY_STYLE } from "./alert-meta";

const KINDS: AlertKind[] = ["after_hours", "unknown_face", "camera_offline", "agent", "arrival", "daily_summary"];
type Range = "today" | "7" | "30" | "custom";

function AlertCard({ a, index }: { a: AlertItem; index: number }) {
  const qc = useQueryClient();
  const lightbox = useLightbox();
  const st = SEVERITY_STYLE[a.severity];
  const kind = KIND_META[a.kind] ?? KIND_META.test;
  const ack = useMutation({
    mutationFn: () => ext.ackAlert(a.id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["alerts"] }),
  });
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.97 }}
      transition={{ delay: Math.min(index, 10) * 0.03 }}
      className={cn("card overflow-hidden", !a.acknowledged && a.severity === "critical" && "ring-1 ring-critical/40")}
    >
      <div className="flex flex-col sm:flex-row">
        {a.clip_url ? (
          <video src={a.clip_url} controls preload="none" poster={a.snapshot_url ?? undefined} className="aspect-video bg-black sm:w-72" />
        ) : a.snapshot_url ? (
          <button onClick={() => lightbox.open([a.snapshot_url as string], 0, a.title)} className="shrink-0 bg-black sm:w-72">
            <img src={a.snapshot_url} alt="" loading="lazy" className="aspect-video w-full object-cover" />
          </button>
        ) : (
          <div className={cn("hidden place-items-center sm:grid sm:w-28", st.soft)}>
            <kind.icon className="size-8" />
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col gap-2 p-4">
          <div className="flex flex-wrap items-center gap-1.5">
            <Badge tone={st.tone === "neutral" ? "accent" : st.tone}>
              <st.icon /> {st.label}
            </Badge>
            <Badge>
              <kind.icon /> {kind.label}
            </Badge>
            {a.channel ? <Badge className="font-mono">{channelLabel(a.channel)}</Badge> : null}
            <span className="ml-auto font-mono text-xs text-fg-muted tabular">{hhmm(a.ts)}</span>
          </div>
          <h3 className="text-sm font-semibold">{a.title}</h3>
          {a.message ? (
            <div className="line-clamp-[8] text-fg-muted [&_div]:text-xs [&_div]:leading-relaxed">
              <Markdown text={a.message} />
            </div>
          ) : null}
          <div className="mt-auto flex justify-end pt-1">
            {a.acknowledged ? (
              <span className="flex items-center gap-1 text-[11px] text-fg-subtle"><Check className="size-3.5" /> ko'rib chiqilgan</span>
            ) : (
              <Button size="sm" onClick={() => ack.mutate()} loading={ack.isPending}>
                <Check /> Ko'rib chiqildi
              </Button>
            )}
          </div>
        </div>
      </div>
    </motion.li>
  );
}

export function AlertsPage() {
  const qc = useQueryClient();
  const [range, setRange] = useState<Range>("7");
  const [custom, setCustom] = useState({ from: shiftDate(todayIso(), -6), to: todayIso() });
  const [kinds, setKinds] = useState<Set<AlertKind>>(new Set());
  const [unacked, setUnacked] = useState(false);

  const from = range === "today" ? todayIso() : range === "7" ? shiftDate(todayIso(), -6) : range === "30" ? shiftDate(todayIso(), -29) : custom.from;
  const to = range === "custom" ? custom.to : todayIso();
  const { data, isLoading } = useAlerts({ from, to, unacked, kind: kinds.size ? [...kinds].join(",") : undefined });

  const ackAll = useMutation({ mutationFn: ext.ackAll, onSuccess: () => void qc.invalidateQueries({ queryKey: ["alerts"] }) });
  const test = useMutation({ mutationFn: ext.testAlert, onError: (e: Error) => toast.error(e.message) });

  const groups = useMemo(() => {
    const m = new Map<string, AlertItem[]>();
    for (const a of data?.items ?? []) {
      const d = a.ts.slice(0, 10);
      m.set(d, [...(m.get(d) ?? []), a]);
    }
    return [...m.entries()];
  }, [data]);

  function toggleKind(k: AlertKind) {
    setKinds((s) => {
      const n = new Set(s);
      if (n.has(k)) n.delete(k);
      else n.add(k);
      return n;
    });
  }

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardBody className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <Segmented
              ariaLabel="Davr"
              value={range}
              onChange={setRange}
              options={[
                { value: "today", label: "Bugun" },
                { value: "7", label: "7 kun" },
                { value: "30", label: "30 kun" },
                { value: "custom", label: "Oraliq" },
              ]}
            />
            {range === "custom" ? (
              <div className="flex items-center gap-2">
                <Input type="date" value={custom.from} max={custom.to} onChange={(e) => setCustom((c) => ({ ...c, from: e.target.value }))} className="h-8 w-40" aria-label="Boshlanish" />
                <span className="text-fg-subtle">—</span>
                <Input type="date" value={custom.to} max={todayIso()} onChange={(e) => setCustom((c) => ({ ...c, to: e.target.value }))} className="h-8 w-40" aria-label="Tugash" />
              </div>
            ) : null}
            <Switch checked={unacked} onChange={setUnacked} label={<span className="text-xs">Faqat ko'rilmaganlar</span>} />
            <div className="ml-auto flex gap-2">
              <Button size="sm" variant="ghost" onClick={() => test.mutate()} loading={test.isPending}>
                <FlaskConical /> Sinov xabari
              </Button>
              <Button size="sm" onClick={() => ackAll.mutate()} disabled={!data?.unread} loading={ackAll.isPending}>
                <CheckCheck /> Hammasini ko'rildi ({data?.unread ?? 0})
              </Button>
            </div>
          </div>
          <div className="flex flex-wrap gap-1.5" role="group" aria-label="Turlar">
            {KINDS.map((k) => {
              const meta = KIND_META[k];
              const on = kinds.has(k);
              return (
                <button
                  key={k}
                  onClick={() => toggleKind(k)}
                  aria-pressed={on}
                  className={cn(
                    "flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition",
                    on ? "border-brand bg-brand-soft text-brand" : "text-fg-muted hover:border-line-strong hover:text-fg",
                  )}
                >
                  <meta.icon className="size-3.5" /> {meta.label}
                </button>
              );
            })}
          </div>
        </CardBody>
      </Card>

      {isLoading ? (
        <div className="space-y-3">{Array.from({ length: 3 }, (_, i) => <Skeleton key={i} className="h-40" />)}</div>
      ) : groups.length ? (
        groups.map(([day, items]) => (
          <section key={day} aria-label={formatDayLong(day)}>
            <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
              {formatDayLong(day)} <span className="text-xs font-normal text-fg-subtle">· {items.length} ta</span>
            </h2>
            <ul className="grid gap-3 xl:grid-cols-2">
              <AnimatePresence mode="popLayout">
                {items.map((a, i) => <AlertCard key={a.id} a={a} index={i} />)}
              </AnimatePresence>
            </ul>
          </section>
        ))
      ) : (
        <EmptyState icon={<ShieldCheck />} title="Hodisa yo'q">
          Tanlangan davrda ogohlantirish qayd etilmagan. Tizim notanish yuzlar va ish vaqtidan tashqari harakatni kuzatib turibdi.
        </EmptyState>
      )}
    </div>
  );
}
