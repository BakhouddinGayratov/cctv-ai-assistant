import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import type { AlertItem, LiveEvent } from "@/lib/types";
import { channelLabel } from "@/lib/utils";

type Listener = (a: AlertItem) => void;
const listeners = new Set<Listener>();

/** Boshqa komponentlar (masalan chat) real-vaqt alertlarga obuna bo'ladi. */
export function subscribeAlerts(fn: Listener): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

const QUIET_KINDS = new Set(["arrival", "daily_summary", "test"]);

/** Bitta EventSource butun ilova uchun; uzilsa brauzer o'zi qayta ulanadi (retry 3 s). */
export function AlertStream() {
  const qc = useQueryClient();
  const navigate = useNavigate();

  useEffect(() => {
    const es = new EventSource("/api/events/stream");
    es.onmessage = (msg) => {
      let ev: LiveEvent;
      try {
        ev = JSON.parse(msg.data) as LiveEvent;
      } catch {
        return;
      }
      void qc.invalidateQueries({ queryKey: ["alerts"] });
      if (ev.type !== "alert") return;
      const a = ev.alert;
      for (const fn of listeners) fn(a);
      if (a.kind === "arrival") void qc.invalidateQueries({ queryKey: ["attendance"] });

      const where = a.channel ? ` · ${channelLabel(a.channel)}` : "";
      const opts = {
        description: `${a.kind_label}${where}${a.message ? ` — ${a.message.slice(0, 120)}` : ""}`,
        action: { label: "Ko'rish", onClick: () => navigate("/alerts") },
        duration: a.severity === "critical" ? 15_000 : 6_000,
      };
      if (a.severity === "critical") toast.error(a.title, opts);
      else if (a.severity === "warning" && !QUIET_KINDS.has(a.kind)) toast.warning(a.title, opts);
      else toast.info(a.title, opts);

      if (a.tts_url) {
        const audio = new Audio(a.tts_url);
        void audio.play().catch(() => undefined); // brauzer avto-ijroni bloklasa — jim o'tkazamiz
      }
    };
    return () => es.close();
  }, [qc, navigate]);

  return null;
}
