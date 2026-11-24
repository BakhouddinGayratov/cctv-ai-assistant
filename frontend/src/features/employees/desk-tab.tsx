import { useMutation } from "@tanstack/react-query";
import { Eraser, ImageOff, RefreshCw, Save, SquareDashedMousePointer } from "lucide-react";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Field, Select } from "@/components/ui/field";
import { Segmented } from "@/components/ui/segmented";
import { api, snapshotUrl } from "@/lib/api";
import { useConfig, useInvalidateStaff } from "@/lib/queries";
import type { Employee } from "@/lib/types";
import { channelLabel } from "@/lib/utils";

type Zone = [number, number, number, number];

export function DeskTab({ employee }: { employee: Employee }) {
  const config = useConfig();
  const invalidate = useInvalidateStaff();
  const [channel, setChannel] = useState<number>(employee.desk_channel ?? config.data?.desk_channels[0] ?? 5);
  const [zone, setZone] = useState<Zone | null>(employee.desk_zone);
  const [mode, setMode] = useState<"room" | "zone">(employee.desk_zone ? "zone" : "room");
  const [src, setSrc] = useState<string>(() => snapshotUrl(channel, true));
  const [imgState, setImgState] = useState<"loading" | "ok" | "error">("loading");
  const imgRef = useRef<HTMLImageElement>(null);
  const startRef = useRef<[number, number] | null>(null);

  useEffect(() => {
    setImgState("loading");
    setSrc(snapshotUrl(channel, true));
  }, [channel]);

  const save = useMutation({
    mutationFn: () => api.setDesk(employee.id, channel, mode === "zone" ? zone : null),
    onSuccess: () => {
      toast.success("Ish joyi saqlandi");
      void invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  function rel(e: PointerEvent): [number, number] {
    const r = (imgRef.current as HTMLImageElement).getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))];
  }

  function onDown(e: PointerEvent<HTMLDivElement>) {
    if (imgState !== "ok" || mode !== "zone") return;
    e.currentTarget.setPointerCapture(e.pointerId);
    const p = rel(e);
    startRef.current = p;
    setZone([p[0], p[1], p[0], p[1]]);
  }
  function onMove(e: PointerEvent) {
    const s = startRef.current;
    if (!s) return;
    const p = rel(e);
    setZone([Math.min(s[0], p[0]), Math.min(s[1], p[1]), Math.max(s[0], p[0]), Math.max(s[1], p[1])]);
  }
  function onUp() {
    startRef.current = null;
    setZone((z) => (z && (z[2] - z[0] < 0.02 || z[3] - z[1] < 0.02) ? null : z));
  }

  return (
    <div className="space-y-5 p-6">
      <Segmented
        ariaLabel="Ish joyi turi"
        value={mode}
        onChange={setMode}
        options={[{ value: "room", label: "Butun xona" }, { value: "zone", label: "Xonadagi joy" }]}
      />

      <div className="flex flex-wrap items-end gap-3">
        <Field label="Xona (kamera)" className="min-w-56 flex-1">
          <Select value={channel} onChange={(e) => setChannel(Number(e.target.value))}>
            {(config.data?.cameras ?? []).map((c) => (
              <option key={c.channel} value={c.channel}>
                {channelLabel(c.channel)} · {c.name}
                {c.roles.includes("desk") ? " (ish joyi bor)" : ""}
              </option>
            ))}
          </Select>
        </Field>
        <Button onClick={() => { setImgState("loading"); setSrc(snapshotUrl(channel, true)); }}>
          <RefreshCw /> Kadrni yangilash
        </Button>
        <Button variant="ghost" onClick={() => setZone(null)} disabled={!zone || mode !== "zone"}>
          <Eraser /> Tozalash
        </Button>
      </div>

      <div className="flex items-start gap-2 rounded-xl border bg-surface-2/60 p-3 text-xs text-fg-muted">
        <SquareDashedMousePointer className="mt-0.5 size-4 shrink-0 text-brand" />
        {mode === "zone"
          ? "Xodim o'tiradigan joyni sichqoncha (yoki barmoq) bilan to'rtburchak qilib belgilang. Shu joyda o'tirgan vaqti ishlagan vaqt hisoblanadi, kameraga orqasini qilib o'tirsa ham."
          : "Xodim shu xonada bo'lgan vaqti ishlagan vaqt hisoblanadi. Xonada bir nechta xodim bo'lsa, har biriga alohida joy belgilash aniqroq natija beradi."}
      </div>

      <div
        className="relative touch-none overflow-hidden rounded-xl border bg-[#05070d] select-none"
        style={{ cursor: imgState === "ok" && mode === "zone" ? "crosshair" : "default" }}
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        onPointerCancel={onUp}
      >
        <img
          ref={imgRef}
          src={src}
          alt="Ish joyi kamerasi kadri"
          draggable={false}
          onLoad={() => setImgState("ok")}
          onError={() => setImgState("error")}
          className="block aspect-video w-full object-contain"
        />
        {imgState !== "ok" ? (
          <div className="absolute inset-0 grid place-items-center text-sm text-white/70">
            {imgState === "loading" ? (
              <span className="skeleton absolute inset-0 opacity-20" />
            ) : (
              <span className="flex flex-col items-center gap-2">
                <ImageOff className="size-8 text-critical" /> Kadr olinmadi — NVR ulanishini tekshiring
              </span>
            )}
          </div>
        ) : null}
        {zone && mode === "zone" ? (
          <div
            className="pointer-events-none absolute rounded-md border-2 border-good bg-good/15 shadow-[0_0_0_9999px_rgb(0_0_0/35%)]"
            style={{ left: `${zone[0] * 100}%`, top: `${zone[1] * 100}%`, width: `${(zone[2] - zone[0]) * 100}%`, height: `${(zone[3] - zone[1]) * 100}%` }}
          >
            <span className="absolute -top-6 left-0 rounded bg-good px-1.5 py-0.5 text-[10px] font-medium text-white">{employee.full_name}</span>
          </div>
        ) : null}
      </div>

      <div className="flex justify-end">
        <Button variant="primary" disabled={mode === "zone" && !zone} onClick={() => save.mutate()} loading={save.isPending}>
          <Save /> Saqlash
        </Button>
      </div>
    </div>
  );
}
