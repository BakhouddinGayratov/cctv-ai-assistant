import { useMutation } from "@tanstack/react-query";
import {
  Clock3, Link2, Monitor, Pencil, ScanFace, Search, Trash2, UserPlus, UserRoundX, UsersRound,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { memo, useDeferredValue, useMemo, useState } from "react";
import { toast } from "sonner";
import { useLightbox } from "@/components/lightbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Modal } from "@/components/ui/dialog";
import { Input, Select } from "@/components/ui/field";
import { Avatar, EmptyState, Skeleton } from "@/components/ui/misc";
import { Segmented } from "@/components/ui/segmented";
import { Tilt } from "@/components/ui/tilt";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useDeleteEmployee, useEmployees, useInvalidateStaff, useUnknown, useWorkers } from "@/lib/queries";
import type { Employee, UnknownSighting } from "@/lib/types";
import { channelLabel, cn } from "@/lib/utils";
import { EmployeeSheet, type SheetTab } from "./employee-sheet";

type Filter = "all" | "active" | "untrained";

const EmployeeCard = memo(function EmployeeCard({
  e,
  index,
  onOpen,
  onDelete,
}: {
  e: Employee;
  index: number;
  onOpen: (e: Employee, tab: SheetTab) => void;
  onDelete: (e: Employee) => void;
}) {
  const trained = e.samples >= 5 ? "good" : e.samples > 0 ? "warning" : "critical";
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 16, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ delay: Math.min(index, 12) * 0.035, type: "spring", stiffness: 300, damping: 28 }}
    >
      <Tilt max={6} className={cn("card h-full overflow-hidden", !e.active && "opacity-60")}>
        <div className="absolute inset-x-0 top-0 h-20 bg-[linear-gradient(135deg,var(--color-brand-soft),transparent_70%)]" />
        <div className="relative flex flex-col gap-4 p-5">
          <div className="flex items-start gap-4">
            <div className="relative">
              <Avatar name={e.full_name} src={e.avatar} size={64} className="rounded-2xl" />
              <span className={cn("absolute -right-1 -bottom-1 grid size-6 place-items-center rounded-lg border-2 border-surface text-white", trained === "good" ? "bg-good" : trained === "warning" ? "bg-warning" : "bg-critical")}>
                <ScanFace className="size-3.5" />
              </span>
            </div>
            <div className="min-w-0 flex-1 pt-1">
              <h3 className="truncate text-[15px] font-semibold tracking-tight">{e.full_name}</h3>
              <p className="truncate text-xs text-fg-muted">{e.position || "Lavozim ko'rsatilmagan"}</p>
              {e.active ? null : <Badge className="mt-1.5">nofaol</Badge>}
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-2 text-[11px]">
            <div className="rounded-lg bg-surface-2 px-2.5 py-2">
              <dt className="flex items-center gap-1 text-fg-subtle"><Clock3 className="size-3" /> Ish vaqti</dt>
              <dd className="mt-0.5 font-mono font-medium tabular">{e.work_start}–{e.work_end}</dd>
            </div>
            <div className="rounded-lg bg-surface-2 px-2.5 py-2">
              <dt className="flex items-center gap-1 text-fg-subtle"><Monitor className="size-3" /> Ish joyi</dt>
              <dd className="mt-0.5 truncate font-medium">{e.desk_channel ? `${channelLabel(e.desk_channel)}${e.desk_zone ? " · joy" : " · butun xona"}` : "—"}</dd>
            </div>
          </dl>
          <Badge tone={trained} className="self-start">
            <ScanFace /> {e.samples ? `${e.samples} ta yuz namunasi` : "Namuna yo'q — tanilmaydi"}
          </Badge>
          <div className="flex gap-1.5">
            <Button size="sm" variant={e.samples ? "secondary" : "primary"} className="flex-1" onClick={() => onOpen(e, "faces")}>
              <ScanFace /> Yuzni o'rgatish
            </Button>
            <Tooltip content="Ish joyi">
              <Button size="icon-sm" aria-label="Ish joyi" onClick={() => onOpen(e, "desk")}>
                <Monitor />
              </Button>
            </Tooltip>
            <Tooltip content="Tahrirlash">
              <Button size="icon-sm" aria-label="Tahrirlash" onClick={() => onOpen(e, "info")}>
                <Pencil />
              </Button>
            </Tooltip>
            <Tooltip content="O'chirish">
              <Button size="icon-sm" variant="danger" aria-label="O'chirish" onClick={() => onDelete(e)}>
                <Trash2 />
              </Button>
            </Tooltip>
          </div>
        </div>
      </Tilt>
    </motion.li>
  );
});

function UnknownCard({ u, employees, index }: { u: UnknownSighting; employees: Employee[]; index: number }) {
  const [target, setTarget] = useState("");
  const invalidate = useInvalidateStaff();
  const lightbox = useLightbox();
  const assign = useMutation({
    mutationFn: () => api.assignSighting(u.id, Number(target)),
    onSuccess: (r) => {
      toast.success(`Biriktirildi${r.retro_identified ? ` · yana ${r.retro_identified} ta ko'rinish tanildi` : ""}`);
      void invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const del = useMutation({
    mutationFn: () => api.deleteSighting(u.id),
    onSuccess: () => void invalidate(),
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <motion.li
      layout
      initial={{ opacity: 0, scale: 0.94 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ delay: Math.min(index, 16) * 0.03 }}
      className="flex flex-col gap-2 rounded-xl border bg-surface-2/60 p-2"
    >
      <button onClick={() => lightbox.open([u.frame_url], 0, `${u.camera} · ${u.ts.slice(11, 16)}`)} className="group relative overflow-hidden rounded-lg" aria-label="To'liq kadrni ko'rish">
        <img src={u.face_url} alt="Notanish yuz" loading="lazy" className="aspect-square w-full object-cover transition-transform duration-300 group-hover:scale-105" />
        <span className="absolute bottom-1 left-1 rounded bg-black/70 px-1.5 py-0.5 font-mono text-[9px] text-white/90">
          {u.ts.slice(5, 16).replace("T", " ")} · {channelLabel(u.channel)}
        </span>
      </button>
      <Select value={target} onChange={(e) => setTarget(e.target.value)} className="h-8 text-xs" aria-label="Xodimni tanlash">
        <option value="">Kim bu?</option>
        {employees.map((e) => (
          <option key={e.id} value={e.id}>
            {e.full_name}
          </option>
        ))}
      </Select>
      <div className="flex gap-1.5">
        <Button size="sm" variant="success" className="flex-1" disabled={!target} loading={assign.isPending} onClick={() => assign.mutate()}>
          <Link2 /> Biriktirish
        </Button>
        <Button size="icon-sm" variant="danger" aria-label="O'chirish" loading={del.isPending} onClick={() => del.mutate()}>
          {del.isPending ? null : <Trash2 />}
        </Button>
      </div>
    </motion.li>
  );
}

export function EmployeesPage() {
  const employees = useEmployees();
  const unknown = useUnknown();
  const workers = useWorkers();
  const remove = useDeleteEmployee();
  const [query, setQuery] = useState("");
  const deferred = useDeferredValue(query);
  const [filter, setFilter] = useState<Filter>("all");
  const [sheet, setSheet] = useState<{ open: boolean; id: number | null; tab: SheetTab }>({ open: false, id: null, tab: "info" });
  const [confirm, setConfirm] = useState<Employee | null>(null);

  const list = employees.data ?? [];
  const current = sheet.id != null ? (list.find((e) => e.id === sheet.id) ?? null) : null;
  const activeList = useMemo(() => list.filter((e) => e.active), [list]);

  const filtered = useMemo(() => {
    const q = deferred.trim().toLowerCase();
    return list.filter((e) => {
      if (filter === "active" && !e.active) return false;
      if (filter === "untrained" && e.samples >= 5) return false;
      return !q || `${e.full_name} ${e.position} ${e.phone}`.toLowerCase().includes(q);
    });
  }, [list, deferred, filter]);

  const open = (e: Employee | null, tab: SheetTab = "info") => setSheet({ open: true, id: e?.id ?? null, tab });
  const fe = workers.data?.face_engine;

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-60 flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-fg-subtle" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ism, lavozim yoki telefon…" className="pl-9" aria-label="Qidirish" />
        </div>
        <Segmented
          ariaLabel="Filtr"
          value={filter}
          onChange={setFilter}
          options={[
            { value: "all", label: `Hammasi (${list.length})` },
            { value: "active", label: "Faol" },
            { value: "untrained", label: "O'rgatilmagan" },
          ]}
        />
        {fe ? (
          <Badge tone={fe.ready ? "good" : "warning"} className="hidden md:inline-flex">
            <ScanFace /> {fe.ready ? `Yuz tanish tayyor · ${fe.samples} namuna · chegara ${fe.threshold}` : fe.error ?? "Yuz tanish tayyor emas"}
          </Badge>
        ) : null}
        <Button variant="primary" className="ml-auto" onClick={() => open(null)}>
          <UserPlus /> Yangi xodim
        </Button>
      </div>

      {employees.isLoading ? (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          {Array.from({ length: 4 }, (_, i) => <Skeleton key={i} className="h-64 rounded-xl" />)}
        </ul>
      ) : filtered.length ? (
        <ul className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
          <AnimatePresence mode="popLayout">
            {filtered.map((e, i) => (
              <EmployeeCard key={e.id} e={e} index={i} onOpen={open} onDelete={setConfirm} />
            ))}
          </AnimatePresence>
        </ul>
      ) : (
        <EmptyState
          icon={<UsersRound />}
          title={list.length ? "Hech narsa topilmadi" : "Hali xodim qo'shilmagan"}
          action={list.length ? null : <Button variant="primary" onClick={() => open(null)}><UserPlus /> Birinchi xodimni qo'shish</Button>}
        >
          {list.length ? "Qidiruv yoki filtrni o'zgartirib ko'ring." : "Xodimni qo'shing va 5–10 ta yuz namunasini o'rgating — tizim uni kirish kameralarida avtomatik taniydi."}
        </EmptyState>
      )}

      <Card>
        <CardHeader
          icon={<UserRoundX />}
          title="Notanish yuzlar"
          description="Oxirgi 7 kunda kirish kameralarida tanilmagan yuzlar. Xodimga biriktirsangiz — tizim uni keyingi safar avtomatik taniydi."
          actions={<Badge tone={unknown.data?.length ? "critical" : "neutral"}>{unknown.data?.length ?? 0} ta</Badge>}
        />
        <CardBody>
          {unknown.isLoading ? (
            <Skeleton className="h-40" />
          ) : unknown.data?.length ? (
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 2xl:grid-cols-8">
              <AnimatePresence mode="popLayout">
                {unknown.data.map((u, i) => (
                  <UnknownCard key={u.id} u={u} employees={activeList} index={i} />
                ))}
              </AnimatePresence>
            </ul>
          ) : (
            <EmptyState icon={<ScanFace />} title="Notanish yuz yo'q">
              Kirish kameralari tanimagan yuzlarni shu yerga yig'adi.
            </EmptyState>
          )}
        </CardBody>
      </Card>

      <EmployeeSheet
        open={sheet.open}
        onOpenChange={(v) => setSheet((s) => ({ ...s, open: v }))}
        employee={current}
        tab={sheet.tab}
        onTabChange={(tab) => setSheet((s) => ({ ...s, tab }))}
        onCreated={(e) => setSheet({ open: true, id: e.id, tab: "faces" })}
      />

      <Modal
        open={confirm != null}
        onOpenChange={(v) => !v && setConfirm(null)}
        title="Xodimni o'chirish"
        description={confirm ? `${confirm.full_name} va uning barcha yuz namunalari o'chiriladi. Oldingi kirish-chiqish yozuvlari "notanish" bo'lib qoladi.` : undefined}
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirm(null)}>
              Bekor qilish
            </Button>
            <Button
              variant="danger"
              loading={remove.isPending}
              onClick={() => confirm && remove.mutate(confirm.id, { onSuccess: () => setConfirm(null) })}
            >
              <Trash2 /> O'chirish
            </Button>
          </>
        }
      >
        {confirm ? (
          <div className="flex items-center gap-4 p-6">
            <Avatar name={confirm.full_name} src={confirm.avatar} size={56} />
            <div>
              <p className="font-medium">{confirm.full_name}</p>
              <p className="text-xs text-fg-muted">{confirm.samples} ta yuz namunasi</p>
            </div>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
