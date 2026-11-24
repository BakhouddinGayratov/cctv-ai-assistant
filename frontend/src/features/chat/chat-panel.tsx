import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ArrowUp, Camera as CameraIcon, CalendarClock, Clapperboard, Sparkles, Trash2, UsersRound, X } from "lucide-react";
import { subscribeAlerts } from "@/features/alerts/alert-stream";
import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { keys, useChatHistory } from "@/lib/queries";
import type { Camera, ChatResponse } from "@/lib/types";
import { channelLabel, cn } from "@/lib/utils";
import { ChatMessage, type ChatMsg } from "./chat-message";

const SUGGESTIONS = [
  { icon: UsersRound, text: "Bugun kim keldi va kim kechikdi?" },
  { icon: CalendarClock, text: "Bu hafta xodimlarning davomati qanday?" },
  { icon: Clapperboard, text: "Bugungi kun uchun 30 sekundlik xulosa klip yarat" },
] as const;

const RE_ARCHIVE = /\d{1,2}[:.]\d{2}|kecha|arxiv/i;
const RE_STAFF = /keldi|ketdi|kechik|ishladi|davomat|xodim|qayerda|effektiv/i;

function pendingLabel(q: string, contextCh: number | null): string {
  if (/xulosa|montaj|klip/i.test(q)) return "Video vazifa yaratilmoqda…";
  if (/qachon|qidir|topib/i.test(q)) return "Arxiv indeksidan qidirilmoqda…";
  if (RE_STAFF.test(q)) return "Davomat ma'lumotlari tahlil qilinmoqda…";
  if (RE_ARCHIVE.test(q)) return "Arxivdan kadrlar olinmoqda…";
  if (/kamera|ch-?\d|\d+-kamera/i.test(q) || contextCh != null) return "Kameradan kadr olinib, AI tahlil qilmoqda…";
  return "O'ylayapman…";
}

let seq = 0;
const nextId = () => `m${Date.now()}-${seq++}`;

export function ChatPanel({ context, onClearContext, className }: { context: Camera | null; onClearContext: () => void; className?: string }) {
  const history = useChatHistory();
  const qc = useQueryClient();
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [draft, setDraft] = useState("");
  const listRef = useRef<HTMLOListElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const seeded = useRef(false);

  useEffect(() => {
    if (seeded.current || !history.data) return;
    seeded.current = true;
    setMessages(history.data.map((t) => ({ id: nextId(), role: t.role, text: t.content })));
  }, [history.data]);

  useEffect(() => {
    const el = listRef.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages]);

  // AI agent va kunlik xulosa xabarlari chatga o'zi tushadi
  useEffect(
    () =>
      subscribeAlerts((a) => {
        if (a.kind !== "agent" && a.kind !== "daily_summary") return;
        const response: ChatResponse = {
          query: "", answer: a.message, mode: "agent", channel: a.channel, camera_name: null,
          snapshot_b64: null, frames_b64: null, video_url: null, time_start: null, time_end: null,
        };
        setMessages((m) => [...m, { id: nextId(), role: "assistant", text: `**${a.title}**\n${a.message}`, response }]);
      }),
    [],
  );

  const send = useMutation({
    mutationFn: ({ query }: { query: string; pendingId: string }) => api.chat(query, context?.channel ?? null),
    onSuccess: (res, { pendingId }) => {
      setMessages((m) => m.map((x) => (x.id === pendingId ? { id: x.id, role: "assistant", text: res.answer, response: res } : x)));
      void qc.invalidateQueries({ queryKey: keys.model });
    },
    onError: (e: Error, { pendingId }) => {
      setMessages((m) => m.map((x) => (x.id === pendingId ? { id: x.id, role: "assistant", text: `Xatolik: ${e.message}`, error: true } : x)));
    },
  });

  const clear = useMutation({
    mutationFn: api.clearChat,
    onSuccess: () => {
      setMessages([]);
      toast.success("Suhbat tozalandi");
    },
  });

  function submit(text: string) {
    const query = text.trim();
    if (!query || send.isPending) return;
    const pendingId = nextId();
    setMessages((m) => [
      ...m,
      { id: nextId(), role: "user", text: query },
      { id: pendingId, role: "assistant", text: "", pending: { label: pendingLabel(query, context?.channel ?? null) } },
    ]);
    setDraft("");
    send.mutate({ query, pendingId });
    requestAnimationFrame(() => inputRef.current?.focus());
  }

  function onKey(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit(draft);
    }
  }

  const empty = messages.length === 0;

  return (
    <section aria-label="AI yordamchi" className={cn("card flex min-h-[520px] flex-col overflow-hidden", className)}>
      <header className="flex items-center gap-3 border-b px-5 py-4">
        <div className="relative grid size-10 place-items-center rounded-xl bg-brand-gradient shadow-glow">
          <Sparkles className="size-5 text-white" />
          <span className="absolute -right-0.5 -bottom-0.5 size-3 rounded-full border-2 border-surface bg-good" />
        </div>
        <div className="min-w-0">
          <h2 className="text-[15px] font-semibold tracking-tight">AI yordamchi</h2>
          <p className="text-xs text-fg-muted">Kameralar, arxiv va davomat bo'yicha savol bering</p>
        </div>
        <Tooltip content="Suhbatni tozalash">
          <Button
            size="icon-sm"
            variant="ghost"
            className="ml-auto"
            aria-label="Suhbatni tozalash"
            disabled={empty || clear.isPending}
            onClick={() => clear.mutate()}
          >
            <Trash2 />
          </Button>
        </Tooltip>
      </header>

      <ol ref={listRef} aria-live="polite" className="flex-1 space-y-4 overflow-y-auto px-4 py-5 sm:px-5">
        {empty ? (
          <motion.li initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="flex flex-col items-center pt-6 text-center">
            <motion.div
              className="grid size-16 place-items-center rounded-2xl bg-brand-gradient shadow-glow"
              animate={{ rotateY: [0, 180, 360] }}
              transition={{ duration: 6, repeat: Infinity, ease: "easeInOut" }}
              style={{ transformPerspective: 600 }}
            >
              <Sparkles className="size-7 text-white" />
            </motion.div>
            <h3 className="mt-4 text-base font-semibold">Assalomu alaykum!</h3>
            <p className="mt-1 max-w-xs text-xs leading-relaxed text-fg-muted">
              Men jonli kadrni tahlil qilaman, arxivni qidiraman va xodimlar davomatini bilaman.
            </p>
            <div className="mt-5 grid w-full gap-2">
              {SUGGESTIONS.map((s, i) => (
                <motion.button
                  key={s.text}
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: 0.15 + i * 0.07 }}
                  whileHover={{ x: 4 }}
                  onClick={() => submit(s.text)}
                  className="flex items-center gap-3 rounded-xl border bg-surface-2 px-3.5 py-2.5 text-left text-xs transition-colors hover:border-brand/40 hover:bg-brand-soft"
                >
                  <s.icon className="size-4 shrink-0 text-brand" />
                  {s.text}
                </motion.button>
              ))}
            </div>
          </motion.li>
        ) : (
          messages.map((m) => <ChatMessage key={m.id} msg={m} />)
        )}
      </ol>

      <div className="border-t p-3 sm:p-4">
        <AnimatePresence>
          {context ? (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="overflow-hidden"
            >
              <div className="mb-2 inline-flex items-center gap-2 rounded-lg border border-brand/25 bg-brand-soft py-1 pr-1 pl-2.5 text-[11px] text-brand">
                <CameraIcon className="size-3.5" />
                Kontekst: <span className="font-mono">{channelLabel(context.channel)}</span> · {context.name}
                <button onClick={onClearContext} aria-label="Kontekstni olib tashlash" className="grid size-5 place-items-center rounded hover:bg-brand/15">
                  <X className="size-3" />
                </button>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(draft);
          }}
          className="flex items-end gap-2 rounded-xl border bg-surface-2 p-1.5 transition focus-within:border-brand focus-within:ring-4 focus-within:ring-brand-soft"
        >
          <label htmlFor="chat-input" className="sr-only">
            Savol
          </label>
          <textarea
            id="chat-input"
            ref={inputRef}
            rows={1}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKey}
            placeholder="Savol yozing… (Enter — yuborish)"
            className="field-sizing-content max-h-36 min-h-9 flex-1 resize-none bg-transparent px-2.5 py-2 text-sm placeholder:text-fg-subtle focus:outline-none"
          />
          <Button type="submit" variant="primary" size="icon" aria-label="Yuborish" loading={send.isPending} disabled={!draft.trim()}>
            {send.isPending ? null : <ArrowUp />}
          </Button>
        </form>
      </div>
    </section>
  );
}
