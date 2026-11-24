import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Map as MapIcon, Plus, Save, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Input, Select } from "@/components/ui/field";
import { ext } from "@/lib/api";
import { useConfig } from "@/lib/queries";
import type { Room } from "@/lib/types";
import { cn } from "@/lib/utils";

function Chips({ items, value, onChange }: { items: { id: number; label: string; title?: string }[]; value: number[]; onChange: (v: number[]) => void }) {
  return (
    <div className="flex flex-wrap gap-1">
      {items.map((it) => {
        const on = value.includes(it.id);
        return (
          <button key={it.id} type="button" title={it.title} aria-pressed={on}
            onClick={() => onChange(on ? value.filter((x) => x !== it.id) : [...value, it.id])}
            className={cn("rounded-md border px-2 py-0.5 text-[11px] transition", on ? "border-brand bg-brand-soft text-brand" : "text-fg-muted hover:border-line-strong")}>
            {it.label}
          </button>
        );
      })}
    </div>
  );
}

/** Ofis xaritasi: xodim qayerdaligini aniqlash uchun xonalar, ularni ko'radigan kameralar va tutash xonalar. */
export function OfficeMapCard() {
  const qc = useQueryClient();
  const config = useConfig();
  const { data } = useQuery({ queryKey: ["rooms"], queryFn: ext.rooms });
  const [draft, setDraft] = useState<Room[] | null>(null);
  const rooms = draft ?? data?.rooms ?? [];
  const save = useMutation({
    mutationFn: () => ext.saveRooms(rooms),
    onSuccess: (d) => {
      qc.setQueryData(["rooms"], d);
      setDraft(null);
      toast.success("Ofis xaritasi saqlandi");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const edit = (i: number, patch: Partial<Room>) => setDraft(rooms.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const cameras = (config.data?.cameras ?? []).map((c) => ({ id: c.channel, label: String(c.channel).padStart(2, "0"), title: c.name }));

  return (
    <Card>
      <CardHeader icon={<MapIcon />} title="Ofis xaritasi"
        description="Xodim boshqa kamera ko'rmaguncha oxirgi xonasida hisoblanadi. Kameralar — xonani ko'radiganlar, tutash — eshik orqali o'tiladigan xonalar"
        actions={<Button size="sm" variant="primary" disabled={!draft} loading={save.isPending} onClick={() => save.mutate()}><Save /> Saqlash</Button>} />
      <CardBody className="space-y-2">
        {rooms.map((r, i) => (
          <div key={r.id ?? `new-${i}`} className="grid gap-2 rounded-xl border p-3 md:grid-cols-[minmax(0,1fr)_170px_auto]">
            <Input value={r.name} onChange={(e) => edit(i, { name: e.target.value })} aria-label="Xona nomi" className="h-8" />
            <Select value={r.kind} onChange={(e) => edit(i, { kind: e.target.value as Room["kind"] })} aria-label="Xona turi" className="h-8">
              {Object.entries(data?.kinds ?? {}).map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            </Select>
            <Button size="icon-sm" variant="ghost" aria-label={`${r.name} xonasini o'chirish`} onClick={() => setDraft(rooms.filter((_, j) => j !== i))}><Trash2 /></Button>
            <div className="md:col-span-3">
              <p className="mb-1 text-[11px] text-fg-subtle">Kameralar</p>
              <Chips items={cameras} value={r.channels} onChange={(v) => edit(i, { channels: v.sort((a, b) => a - b) })} />
            </div>
            {r.id != null ? (
              <div className="md:col-span-3">
                <p className="mb-1 text-[11px] text-fg-subtle">Tutash xonalar</p>
                <Chips items={rooms.filter((o) => o.id != null && o.id !== r.id).map((o) => ({ id: o.id as number, label: o.name }))}
                  value={r.neighbors} onChange={(v) => edit(i, { neighbors: v })} />
              </div>
            ) : <p className="text-[11px] text-fg-subtle md:col-span-3">Saqlangach tutash xonalarni tanlash mumkin</p>}
          </div>
        ))}
        <Button size="sm" onClick={() => setDraft([...rooms, { id: null, name: "Yangi xona", kind: "work", channels: [], neighbors: [] }])}><Plus /> Xona qo'shish</Button>
      </CardBody>
    </Card>
  );
}
