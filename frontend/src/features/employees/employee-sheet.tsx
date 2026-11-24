import { IdCard, MonitorCog, ScanFace, Save } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { Sheet } from "@/components/ui/dialog";
import { Field, Input, Select, Switch } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { useQuery } from "@tanstack/react-query";
import { ext } from "@/lib/api";
import { useConfig, useSaveEmployee } from "@/lib/queries";
import type { Employee, EmployeeInput } from "@/lib/types";
import { channelLabel } from "@/lib/utils";
import { DeskTab } from "./desk-tab";
import { FacesTab } from "./faces-tab";

export type SheetTab = "info" | "faces" | "desk";

function InfoForm({ employee, onSaved }: { employee: Employee | null; onSaved: (e: Employee) => void }) {
  const config = useConfig();
  const save = useSaveEmployee();
  const [form, setForm] = useState<EmployeeInput>(() => ({
    first_name: employee?.first_name ?? "",
    last_name: employee?.last_name ?? "",
    position: employee?.position ?? "",
    phone: employee?.phone ?? "",
    work_start: employee?.work_start ?? config.data?.default_work_start ?? "09:00",
    work_end: employee?.work_end ?? config.data?.default_work_end ?? "18:00",
    active: employee?.active ?? true,
    desk_channel: employee?.desk_channel ?? null,
    room_id: employee?.room_id ?? null,
  }));
  const rooms = useQuery({ queryKey: ["rooms"], queryFn: ext.rooms });
  const [error, setError] = useState<string | null>(null);
  const set = <K extends keyof EmployeeInput>(k: K, v: EmployeeInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!form.first_name.trim()) {
      setError("Ism kiritilishi shart");
      return;
    }
    if (form.work_end <= form.work_start) {
      setError("Ish tugash vaqti boshlanishidan keyin bo'lishi kerak");
      return;
    }
    setError(null);
    save.mutate(
      { id: employee?.id ?? null, body: { ...form, first_name: form.first_name.trim(), last_name: form.last_name.trim() } },
      { onSuccess: onSaved },
    );
  }

  return (
    <form onSubmit={submit} className="grid gap-4 p-6 sm:grid-cols-2">
      <Field label="Ism *" error={error && !form.first_name.trim() ? error : null}>
        <Input autoFocus value={form.first_name} onChange={(e) => set("first_name", e.target.value)} autoComplete="given-name" placeholder="Bahodir" />
      </Field>
      <Field label="Familiya">
        <Input value={form.last_name} onChange={(e) => set("last_name", e.target.value)} autoComplete="family-name" placeholder="Aliyev" />
      </Field>
      <Field label="Lavozim">
        <Input value={form.position} onChange={(e) => set("position", e.target.value)} placeholder="Menejer" />
      </Field>
      <Field label="Telefon">
        <Input type="tel" inputMode="tel" value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="+998 90 123 45 67" />
      </Field>
      <Field label="Ish boshlanishi" hint="Kechikish shu vaqtdan hisoblanadi">
        <Input type="time" value={form.work_start} onChange={(e) => set("work_start", e.target.value)} />
      </Field>
      <Field label="Ish tugashi" error={error && form.first_name.trim() ? error : null}>
        <Input type="time" value={form.work_end} onChange={(e) => set("work_end", e.target.value)} />
      </Field>
      <Field label="O'z xonasi" className="sm:col-span-2" hint="Boshqa kamera ko'rmaguncha shu xonada ishlayapti deb hisoblanadi. Xonalar — Sozlamalar → Ofis xaritasi">
        <Select value={form.room_id ?? ""} onChange={(e) => set("room_id", e.target.value ? Number(e.target.value) : null)}>
          <option value="">— belgilanmagan —</option>
          {(rooms.data?.rooms ?? []).map((r) => (
            <option key={r.id} value={r.id ?? ""}>{r.name}{r.channels.length ? ` · ${r.channels.map(channelLabel).join(", ")}` : " · kamerasiz"}</option>
          ))}
        </Select>
      </Field>
      <div className="sm:col-span-2">
        <Switch checked={form.active} onChange={(v) => set("active", v)} label="Faol — kuzatuv va davomatda qatnashadi" />
      </div>
      <div className="flex justify-end sm:col-span-2">
        <Button type="submit" variant="primary" loading={save.isPending}>
          <Save /> {employee ? "Saqlash" : "Qo'shish va yuzni o'rgatish"}
        </Button>
      </div>
    </form>
  );
}

export function EmployeeSheet({
  open,
  onOpenChange,
  employee,
  tab,
  onTabChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  employee: Employee | null;
  tab: SheetTab;
  onTabChange: (t: SheetTab) => void;
  onCreated: (e: Employee) => void;
}) {
  const isNew = employee == null;
  const [formKey, setFormKey] = useState(0);
  useEffect(() => {
    if (open) setFormKey((k) => k + 1);
  }, [open, employee?.id]);

  return (
    <Sheet
      open={open}
      onOpenChange={onOpenChange}
      title={isNew ? "Yangi xodim" : employee.full_name}
      description={isNew ? "Ma'lumotlarni kiriting — keyin yuz namunalarini qo'shasiz." : employee.position || "Xodim sozlamalari"}
    >
      {isNew ? null : (
        <div className="border-b px-6 py-3">
          <Segmented
            ariaLabel="Bo'limlar"
            value={tab}
            onChange={onTabChange}
            options={[
              { value: "info", label: "Ma'lumot", icon: <IdCard /> },
              { value: "faces", label: `Yuz namunalari (${employee.samples})`, icon: <ScanFace /> },
              { value: "desk", label: "Ish joyi", icon: <MonitorCog /> },
            ]}
          />
        </div>
      )}
      <AnimatePresence mode="wait">
        <motion.div
          key={isNew ? "new" : `${employee.id}-${tab}`}
          initial={{ opacity: 0, x: 12 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -12 }}
          transition={{ duration: 0.18 }}
        >
          {isNew || tab === "info" ? (
            <InfoForm key={formKey} employee={employee} onSaved={(e) => (isNew ? onCreated(e) : undefined)} />
          ) : tab === "faces" ? (
            <FacesTab employeeId={employee.id} />
          ) : (
            <DeskTab employee={employee} />
          )}
        </motion.div>
      </AnimatePresence>
    </Sheet>
  );
}
