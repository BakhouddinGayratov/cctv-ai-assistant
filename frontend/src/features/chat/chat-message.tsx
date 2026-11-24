import { BellRing, Bot, CircleAlert, Clapperboard, Download, History, MessageSquareText, Radio, Search, UsersRound } from "lucide-react";
import { motion } from "motion/react";
import { memo } from "react";
import { Link } from "react-router";
import { JobProgress } from "@/components/job-progress";
import { useLightbox } from "@/components/lightbox";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { b64Jpeg } from "@/lib/api";
import type { ChatMode, ChatResponse } from "@/lib/types";
import { channelLabel, cn } from "@/lib/utils";
import { Markdown } from "./markdown";

export interface ChatMsg {
  id: string;
  role: "user" | "assistant";
  text: string;
  response?: ChatResponse;
  pending?: { label: string };
  error?: boolean;
}

const MODE: Record<ChatMode, { label: string; tone: BadgeTone; icon: typeof Radio }> = {
  live: { label: "Jonli kadr", tone: "critical", icon: Radio },
  playback: { label: "Arxiv", tone: "warning", icon: History },
  staff: { label: "Davomat", tone: "good", icon: UsersRound },
  general: { label: "Umumiy", tone: "brand", icon: MessageSquareText },
  job: { label: "Video vazifa", tone: "accent", icon: Clapperboard },
  search: { label: "Arxiv qidiruvi", tone: "accent", icon: Search },
  agent: { label: "AI agent", tone: "brand", icon: BellRing },
};

function SearchResults({ r }: { r: ChatResponse }) {
  const lightbox = useLightbox();
  const hits = r.results ?? [];
  if (!hits.length) return null;
  const images = hits.map((h) => h.image).filter((x): x is string => !!x);
  return (
    <ul className="mt-3 grid grid-cols-2 gap-2">
      {hits.map((h) => (
        <li key={`${h.ts}-${h.channel}`} className="overflow-hidden rounded-lg border bg-surface">
          {h.image ? (
            <button className="block w-full" onClick={() => lightbox.open(images, Math.max(0, images.indexOf(h.image as string)))}>
              <img src={h.image} alt="" loading="lazy" className="aspect-video w-full object-cover" />
            </button>
          ) : null}
          <div className="p-2">
            <p className="font-mono text-[10px] text-fg-subtle">
              {h.ts.slice(5, 16).replace("T", " ")} · {channelLabel(h.channel)}
            </p>
            <p className="mt-0.5 line-clamp-2 text-[11px] leading-snug">{h.text}</p>
            <Link to={`/archive?channel=${h.channel}&day=${h.ts.slice(0, 10)}&at=${h.ts.slice(11, 16)}`} className="mt-1 inline-block text-[11px] font-medium text-brand hover:underline">
              Arxivda ochish →
            </Link>
          </div>
        </li>
      ))}
    </ul>
  );
}

function Gallery({ r }: { r: ChatResponse }) {
  const lightbox = useLightbox();
  const imgs = (r.frames_b64?.length ? r.frames_b64 : r.snapshot_b64 ? [r.snapshot_b64] : []).map(b64Jpeg);
  if (!imgs.length) return null;
  const single = imgs.length === 1;
  return (
    <div className={cn("mt-3 grid gap-1.5", single ? "grid-cols-1" : imgs.length === 2 ? "grid-cols-2" : "grid-cols-3")}>
      {imgs.map((src, i) => (
        <button
          key={i}
          onClick={() => lightbox.open(imgs, i, r.camera_name ?? undefined)}
          className="group relative overflow-hidden rounded-lg border bg-black"
          aria-label={`Kadr ${i + 1} ni kattalashtirish`}
        >
          <img src={src} alt="" loading="lazy" className={cn("w-full object-cover transition-transform duration-500 group-hover:scale-105", single ? "aspect-video" : "aspect-[4/3]")} />
        </button>
      ))}
    </div>
  );
}

function Thinking({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-3 text-sm text-fg-muted">
      <span className="flex gap-1" aria-hidden>
        {[0, 1, 2].map((i) => (
          <motion.span
            key={i}
            className="size-1.5 rounded-full bg-brand"
            animate={{ y: [0, -4, 0], opacity: [0.4, 1, 0.4] }}
            transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.15 }}
          />
        ))}
      </span>
      <span role="status">{label}</span>
    </div>
  );
}

export const ChatMessage = memo(function ChatMessage({ msg }: { msg: ChatMsg }) {
  if (msg.role === "user") {
    return (
      <motion.li
        layout="position"
        initial={{ opacity: 0, y: 12, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ type: "spring", stiffness: 420, damping: 32 }}
        className="flex justify-end"
      >
        <div className="max-w-[86%] rounded-2xl rounded-br-md bg-brand-gradient px-4 py-2.5 text-[13.5px] leading-relaxed text-white shadow-glow">
          {msg.text}
        </div>
      </motion.li>
    );
  }

  const r = msg.response;
  const mode = r ? MODE[r.mode] : null;
  return (
    <motion.li
      layout="position"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring", stiffness: 380, damping: 32 }}
      className="flex gap-2.5"
    >
      <span className={cn("mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl", msg.error ? "bg-critical-soft text-critical" : "bg-brand-gradient text-white")}>
        {msg.error ? <CircleAlert className="size-4" /> : <Bot className="size-4" />}
      </span>
      <div className={cn("min-w-0 max-w-[92%] flex-1 rounded-2xl rounded-tl-md border bg-surface-2 px-4 py-3", msg.error && "border-critical/30")}>
        {msg.pending ? (
          <Thinking label={msg.pending.label} />
        ) : (
          <>
            {mode ? (
              <div className="mb-2 flex flex-wrap items-center gap-1.5">
                <Badge tone={mode.tone}>
                  <mode.icon /> {mode.label}
                </Badge>
                {r?.channel ? <Badge className="font-mono">{channelLabel(r.channel)}</Badge> : null}
                {r?.camera_name ? <span className="truncate text-[11px] text-fg-subtle">{r.camera_name}</span> : null}
              </div>
            ) : null}
            <Markdown text={msg.text} />
            {r ? <Gallery r={r} /> : null}
            {r ? <SearchResults r={r} /> : null}
            {r?.job ? <JobProgress initial={r.job} compact /> : null}
            {r?.video_url ? (
              <div className="mt-3 overflow-hidden rounded-lg border">
                <video src={r.video_url} controls preload="metadata" className="aspect-video w-full bg-black" />
                <a href={r.video_url} download className="flex items-center gap-1.5 bg-surface px-3 py-1.5 text-xs text-brand hover:underline">
                  <Clapperboard className="size-3.5" /> MP4 klip <Download className="ml-auto size-3.5" />
                </a>
              </div>
            ) : null}
          </>
        )}
      </div>
    </motion.li>
  );
});
