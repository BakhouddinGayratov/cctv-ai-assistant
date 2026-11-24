import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Camera as CameraIcon, CheckCircle2, ImagePlus, Trash2, UploadCloud, XCircle } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRef, useState, type DragEvent } from "react";
import { toast } from "sonner";
import { useLightbox } from "@/components/lightbox";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select } from "@/components/ui/field";
import { EmptyState, Skeleton } from "@/components/ui/misc";
import { api, b64Jpeg } from "@/lib/api";
import { keys, useConfig, useFaces, useInvalidateStaff } from "@/lib/queries";
import type { CaptureResponse, UploadResult } from "@/lib/types";
import { channelLabel, cn } from "@/lib/utils";

const SOURCE: Record<string, string> = { upload: "yuklangan", camera: "kameradan", sighting: "kirishdan" };

export function FacesTab({ employeeId }: { employeeId: number }) {
  const faces = useFaces(employeeId);
  const config = useConfig();
  const qc = useQueryClient();
  const invalidateStaff = useInvalidateStaff();
  const lightbox = useLightbox();
  const fileRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [channel, setChannel] = useState<number>(config.data?.attendance_channels.at(-1) ?? 2);
  const [capture, setCapture] = useState<CaptureResponse | null>(null);

  const refresh = () => Promise.all([qc.invalidateQueries({ queryKey: keys.faces(employeeId) }), invalidateStaff()]);

  const upload = useMutation({
    mutationFn: (files: File[]) => api.uploadFaces(employeeId, files),
    onSuccess: (res) => {
      setUploadResult(res);
      const ok = res.results.filter((r) => r.ok).length;
      if (ok) toast.success(`${ok} ta namuna qo'shildi${res.retro_identified ? ` · ${res.retro_identified} ta ko'rinish tanildi` : ""}`);
      void refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const capt = useMutation({
    mutationFn: () => api.captureFaces(channel),
    onSuccess: setCapture,
    onError: (e: Error) => toast.error(e.message),
  });

  const pick = useMutation({
    mutationFn: (index: number) => api.faceFromCapture(employeeId, capture?.token ?? "", index),
    onSuccess: (res) => {
      toast.success(`Namuna qo'shildi${res.retro_identified ? ` · ${res.retro_identified} ta ko'rinish tanildi` : ""}`);
      void refresh();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: api.deleteFace,
    onSuccess: () => void refresh(),
    onError: (e: Error) => toast.error(e.message),
  });

  function onFiles(list: FileList | null) {
    const files = Array.from(list ?? []).filter((f) => f.type.startsWith("image/"));
    if (files.length) upload.mutate(files);
  }

  function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    onFiles(e.dataTransfer.files);
  }

  const count = faces.data?.length ?? 0;

  return (
    <div className="space-y-6 p-6">
      <section>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-semibold">Namunalar</h3>
          <Badge tone={count >= 5 ? "good" : count > 0 ? "warning" : "critical"}>
            {count} ta {count < 5 ? "· 5–10 tavsiya" : "· yetarli"}
          </Badge>
        </div>
        {faces.isLoading ? (
          <div className="grid grid-cols-4 gap-2 sm:grid-cols-6">
            {Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="aspect-square" />)}
          </div>
        ) : count ? (
          <ul className="grid grid-cols-4 gap-2 sm:grid-cols-6">
            <AnimatePresence initial={false}>
              {faces.data?.map((f, i) => (
                <motion.li
                  key={f.id}
                  layout
                  initial={{ opacity: 0, scale: 0.8 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.8 }}
                  className="group relative"
                >
                  <button onClick={() => lightbox.open(faces.data?.map((x) => x.url) ?? [], i)} className="block w-full overflow-hidden rounded-lg border">
                    <img src={f.url} alt="Yuz namunasi" loading="lazy" className="aspect-square w-full object-cover transition-transform group-hover:scale-105" />
                  </button>
                  <span className="pointer-events-none absolute bottom-1 left-1 rounded bg-black/65 px-1 text-[9px] text-white/85">{SOURCE[f.source] ?? f.source}</span>
                  <button
                    onClick={() => remove.mutate(f.id)}
                    aria-label="Namunani o'chirish"
                    className="absolute top-1 right-1 grid size-6 place-items-center rounded-md bg-critical text-white opacity-0 shadow transition-opacity group-hover:opacity-100 focus:opacity-100"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </motion.li>
              ))}
            </AnimatePresence>
          </ul>
        ) : (
          <EmptyState icon={<ImagePlus />} title="Hali namuna yo'q">
            Namunasiz xodim tanilmaydi. Quyidan rasm yuklang yoki kameradan oling.
          </EmptyState>
        )}
      </section>

      <div className="grid gap-4 md:grid-cols-2">
        <section
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={cn(
            "flex flex-col items-center justify-center gap-3 rounded-xl border-2 border-dashed p-6 text-center transition-colors",
            dragging ? "border-brand bg-brand-soft" : "hover:border-line-strong",
          )}
        >
          <motion.span animate={dragging ? { y: -4, scale: 1.1 } : { y: 0, scale: 1 }} className="grid size-12 place-items-center rounded-2xl bg-brand-soft text-brand">
            <UploadCloud className="size-6" />
          </motion.span>
          <div>
            <p className="text-sm font-medium">Rasmlarni shu yerga tashlang</p>
            <p className="mt-1 text-xs text-fg-subtle">Har rasmdagi eng katta yuz olinadi</p>
          </div>
          <input ref={fileRef} type="file" accept="image/*" multiple hidden onChange={(e) => onFiles(e.target.files)} />
          <Button size="sm" onClick={() => fileRef.current?.click()} loading={upload.isPending}>
            Fayl tanlash
          </Button>
          {uploadResult ? (
            <ul className="w-full space-y-1 text-left text-[11px]">
              {uploadResult.results.map((r) => (
                <li key={r.file} className={cn("flex items-start gap-1.5", r.ok ? "text-good" : "text-critical")}>
                  {r.ok ? <CheckCircle2 className="mt-px size-3.5 shrink-0" /> : <XCircle className="mt-px size-3.5 shrink-0" />}
                  <span className="truncate">{r.file}</span>
                  {r.reason ? <span className="text-fg-subtle">— {r.reason}</span> : null}
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <section className="flex flex-col gap-3 rounded-xl border p-5">
          <div className="flex items-center gap-2">
            <span className="grid size-9 place-items-center rounded-lg bg-good-soft text-good">
              <CameraIcon className="size-[18px]" />
            </span>
            <div>
              <p className="text-sm font-medium">Kameradan olish</p>
              <p className="text-[11px] text-fg-subtle">Eng aniq natija — kirish kamerasining o'zidan</p>
            </div>
          </div>
          <Select value={channel} onChange={(e) => setChannel(Number(e.target.value))} aria-label="Kamera">
            {(config.data?.cameras ?? []).map((c) => (
              <option key={c.channel} value={c.channel}>
                {channelLabel(c.channel)} · {c.name}
                {c.roles.includes("entrance") ? " (kirish)" : ""}
              </option>
            ))}
          </Select>
          <Button variant="success" onClick={() => capt.mutate()} loading={capt.isPending}>
            <CameraIcon /> Kadr olish
          </Button>
          <p className="text-[11px] leading-relaxed text-fg-subtle">Xodim kamera oldida yuzini qaratib tursin, keyin kadr oling va quyida uning yuzini tanlang.</p>
        </section>
      </div>

      <AnimatePresence>
        {capture ? (
          <motion.section initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="space-y-3">
            <button onClick={() => lightbox.open([b64Jpeg(capture.image_b64)])} className="block w-full overflow-hidden rounded-xl border">
              <img src={b64Jpeg(capture.image_b64)} alt="Olingan kadr" className="w-full" />
            </button>
            <h4 className="text-sm font-medium">{capture.faces.length ? "Qaysi biri shu xodim?" : "Kadrda yuz topilmadi"}</h4>
            <div className="flex flex-wrap gap-3">
              {capture.faces.map((f) => (
                <motion.button
                  key={f.index}
                  whileHover={f.too_small ? undefined : { y: -3 }}
                  whileTap={f.too_small ? undefined : { scale: 0.96 }}
                  disabled={f.too_small || pick.isPending}
                  onClick={() => pick.mutate(f.index)}
                  className={cn(
                    "flex w-28 flex-col items-center gap-1.5 rounded-xl border p-2 transition-colors",
                    f.too_small ? "cursor-not-allowed opacity-50" : "hover:border-good hover:bg-good-soft",
                  )}
                >
                  <img src={b64Jpeg(f.crop_b64)} alt="" className="aspect-square w-full rounded-lg object-cover" />
                  <span className={cn("text-[10px]", f.name ? "text-good" : "text-fg-subtle")}>
                    {f.name ? `${f.name} ${Math.round(f.similarity * 100)}%` : f.too_small ? `kichik ${f.size}` : `notanish ${f.size}`}
                  </span>
                </motion.button>
              ))}
            </div>
          </motion.section>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
