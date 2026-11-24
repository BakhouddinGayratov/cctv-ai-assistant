import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ext } from "@/lib/api";
import { useAlerts } from "@/lib/queries";
import { channelLabel, cn, hhmm } from "@/lib/utils";
import { SEVERITY_STYLE } from "./alert-meta";

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const qc = useQueryClient();
  const { data } = useAlerts({ unacked: true });
  const unread = data?.unread ?? 0;
  const items = (data?.items ?? []).filter((a) => a.kind !== "arrival" && a.kind !== "daily_summary").slice(0, 8);

  const ackAll = useMutation({
    mutationFn: ext.ackAll,
    onSuccess: () => void qc.invalidateQueries({ queryKey: ["alerts"] }),
  });

  useEffect(() => {
    if (!open) return;
    const onDown = (e: PointerEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={`Ogohlantirishlar${unread ? `, ${unread} ta o'qilmagan` : ""}`}
        aria-expanded={open}
        className="relative grid size-9 place-items-center rounded-lg border text-fg-muted transition hover:bg-surface-2 hover:text-fg"
      >
        <motion.span key={unread} animate={unread ? { rotate: [0, -14, 12, -8, 0] } : {}} transition={{ duration: 0.6 }}>
          <Bell className="size-4" />
        </motion.span>
        <AnimatePresence>
          {unread ? (
            <motion.span
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              exit={{ scale: 0 }}
              className="absolute -top-1.5 -right-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-critical px-1 text-[10px] font-bold text-white"
            >
              {unread > 99 ? "99+" : unread}
            </motion.span>
          ) : null}
        </AnimatePresence>
      </button>

      <AnimatePresence>
        {open ? (
          <motion.div
            initial={{ opacity: 0, y: -6, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -6, scale: 0.97 }}
            transition={{ duration: 0.16 }}
            className="absolute right-0 z-50 mt-2 w-[min(380px,calc(100vw-2rem))] origin-top-right overflow-hidden rounded-xl border bg-surface shadow-pop"
          >
            <div className="flex items-center justify-between border-b px-4 py-3">
              <p className="text-sm font-semibold">Ogohlantirishlar</p>
              <button
                onClick={() => ackAll.mutate()}
                disabled={!unread}
                className="flex items-center gap-1 text-xs text-brand hover:underline disabled:opacity-40 disabled:no-underline"
              >
                <CheckCheck className="size-3.5" /> Hammasini o'qildi
              </button>
            </div>
            <ul className="max-h-96 overflow-y-auto">
              {items.length ? (
                items.map((a) => {
                  const st = SEVERITY_STYLE[a.severity];
                  return (
                    <li key={a.id}>
                      <Link to="/alerts" onClick={() => setOpen(false)} className="flex gap-3 border-b px-4 py-3 transition hover:bg-surface-2">
                        {a.snapshot_url ? (
                          <img src={a.snapshot_url} alt="" className="size-11 shrink-0 rounded-lg object-cover" />
                        ) : (
                          <span className={cn("grid size-11 shrink-0 place-items-center rounded-lg", st.soft)}>
                            <st.icon className="size-5" />
                          </span>
                        )}
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{a.title}</p>
                          <p className="truncate text-[11px] text-fg-subtle">
                            {hhmm(a.ts)} · {a.kind_label}
                            {a.channel ? ` · ${channelLabel(a.channel)}` : ""}
                          </p>
                        </div>
                        <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", st.dot)} />
                      </Link>
                    </li>
                  );
                })
              ) : (
                <li className="px-4 py-10 text-center text-xs text-fg-subtle">Yangi ogohlantirish yo'q</li>
              )}
            </ul>
            <Link to="/alerts" onClick={() => setOpen(false)} className="block px-4 py-2.5 text-center text-xs font-medium text-brand hover:bg-surface-2">
              Barcha hodisalar →
            </Link>
          </motion.div>
        ) : null}
      </AnimatePresence>
    </div>
  );
}
