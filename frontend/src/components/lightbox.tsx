import * as Dialog from "@radix-ui/react-dialog";
import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { createContext, use, useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

interface LightboxState {
  images: string[];
  index: number;
  caption?: string;
}

interface LightboxCtx {
  open: (images: string[], index?: number, caption?: string) => void;
}

const Ctx = createContext<LightboxCtx | null>(null);

export function useLightbox(): LightboxCtx {
  const ctx = use(Ctx);
  if (!ctx) throw new Error("useLightbox LightboxProvider ichida ishlatilishi kerak");
  return ctx;
}

export function LightboxProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<LightboxState | null>(null);
  const open = useCallback((images: string[], index = 0, caption?: string) => setState({ images, index, caption }), []);
  const value = useMemo(() => ({ open }), [open]);
  const count = state?.images.length ?? 0;

  const go = useCallback(
    (delta: number) => setState((s) => (s ? { ...s, index: (s.index + delta + s.images.length) % s.images.length } : s)),
    [],
  );

  useEffect(() => {
    if (!state || count < 2) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") go(1);
      if (e.key === "ArrowLeft") go(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state, count, go]);

  const src = state?.images[state.index];

  return (
    <Ctx value={value}>
      {children}
      <Dialog.Root open={state != null} onOpenChange={(o) => !o && setState(null)}>
        <AnimatePresence>
          {state && src ? (
            <Dialog.Portal forceMount>
              <Dialog.Overlay asChild forceMount>
                <motion.div
                  className="fixed inset-0 z-[70] bg-black/85 backdrop-blur-md"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                />
              </Dialog.Overlay>
              <Dialog.Content asChild forceMount aria-describedby={undefined}>
                <motion.div
                  className="fixed inset-0 z-[70] flex flex-col items-center justify-center gap-3 p-4"
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.97 }}
                  transition={{ type: "spring", stiffness: 360, damping: 32 }}
                  onClick={(e) => e.target === e.currentTarget && setState(null)}
                >
                  <Dialog.Title className="sr-only">Rasm</Dialog.Title>
                  <AnimatePresence mode="wait">
                    <motion.img
                      key={src}
                      src={src}
                      alt={state.caption ?? "Kamera kadri"}
                      className="max-h-[80dvh] max-w-full rounded-xl border border-white/10 object-contain shadow-2xl"
                      initial={{ opacity: 0, x: 20 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -20 }}
                      transition={{ duration: 0.18 }}
                    />
                  </AnimatePresence>
                  <div className="flex items-center gap-2 rounded-xl border border-white/10 bg-black/60 px-2 py-1.5 text-white">
                    {count > 1 ? (
                      <button aria-label="Oldingi" onClick={() => go(-1)} className="grid size-8 place-items-center rounded-lg hover:bg-white/10">
                        <ChevronLeft className="size-4" />
                      </button>
                    ) : null}
                    <span className="px-2 font-mono text-xs text-white/70">
                      {count > 1 ? `${state.index + 1} / ${count}` : state.caption ?? "Kadr"}
                    </span>
                    {count > 1 ? (
                      <button aria-label="Keyingi" onClick={() => go(1)} className="grid size-8 place-items-center rounded-lg hover:bg-white/10">
                        <ChevronRight className="size-4" />
                      </button>
                    ) : null}
                    <a href={src} download="kadr.jpg" aria-label="Yuklab olish" className="grid size-8 place-items-center rounded-lg hover:bg-white/10">
                      <Download className="size-4" />
                    </a>
                    <Dialog.Close aria-label="Yopish" className="grid size-8 place-items-center rounded-lg hover:bg-white/10">
                      <X className="size-4" />
                    </Dialog.Close>
                  </div>
                </motion.div>
              </Dialog.Content>
            </Dialog.Portal>
          ) : null}
        </AnimatePresence>
      </Dialog.Root>
    </Ctx>
  );
}
