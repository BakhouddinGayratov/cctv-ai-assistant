import { CircleAlert, Clapperboard, Download, LoaderCircle } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useJob } from "@/lib/queries";
import type { JobInfo } from "@/lib/types";
import { channelLabel, cn } from "@/lib/utils";

/** Fon vazifasi (klip / video xulosa) progressi; tugagach video pleer. */
export function JobProgress({ initial, compact }: { initial: JobInfo; compact?: boolean }) {
  const { data } = useJob(initial.id);
  const job = data ?? initial;
  const pct = Math.round(job.progress * 100);

  return (
    <div className={cn("overflow-hidden rounded-xl border bg-surface", compact ? "mt-3" : "")}>
      <AnimatePresence mode="wait">
        {job.status === "done" && job.result?.url ? (
          <motion.div key="done" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}>
            <video src={job.result.url} controls preload="metadata" className="aspect-video w-full bg-black" />
            <div className="flex items-center gap-2 px-3 py-2 text-xs">
              <Clapperboard className="size-3.5 text-brand" />
              <span className="truncate text-fg-muted">{job.message}</span>
              <a href={job.result.url} download className="ml-auto flex items-center gap-1 font-medium text-brand hover:underline">
                <Download className="size-3.5" /> Yuklab olish
              </a>
            </div>
            {job.result.moments?.length ? (
              <ol className="max-h-40 space-y-1 overflow-y-auto border-t px-3 py-2 text-[11px]">
                {job.result.moments.map((m) => (
                  <li key={`${m.ts}-${m.channel}`} className="flex gap-2 text-fg-muted">
                    <span className="font-mono tabular text-fg">{m.ts.slice(11, 19)}</span>
                    <span className="font-mono">{channelLabel(m.channel)}</span>
                    <span className="truncate">{m.label}</span>
                  </li>
                ))}
              </ol>
            ) : null}
          </motion.div>
        ) : job.status === "error" ? (
          <motion.div key="err" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex items-start gap-2 p-3 text-xs text-critical">
            <CircleAlert className="mt-0.5 size-4 shrink-0" /> {job.message}
          </motion.div>
        ) : (
          <motion.div key="run" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="p-3">
            <div className="flex items-center gap-2 text-xs">
              <LoaderCircle className="size-3.5 animate-spin text-brand" />
              <span className="truncate font-medium">{job.title}</span>
              <span className="ml-auto font-mono text-fg-muted tabular">{Math.round(job.elapsed)}s</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-3" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
              <motion.div className="h-full rounded-full bg-brand-gradient" animate={{ width: `${Math.max(4, pct)}%` }} transition={{ ease: "easeOut" }} />
            </div>
            <p className="mt-1.5 text-[11px] text-fg-subtle">{job.message}</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
