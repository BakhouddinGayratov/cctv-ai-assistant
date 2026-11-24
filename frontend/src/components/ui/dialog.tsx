import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface BaseProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: ReactNode;
  description?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  className?: string;
}

function Header({ title, description }: Pick<BaseProps, "title" | "description">) {
  return (
    <div className="flex items-start justify-between gap-4 border-b px-6 py-4">
      <div className="min-w-0">
        <Dialog.Title className="text-base font-semibold tracking-tight">{title}</Dialog.Title>
        {description ? (
          <Dialog.Description className="mt-1 text-xs leading-relaxed text-fg-muted">{description}</Dialog.Description>
        ) : (
          <Dialog.Description className="sr-only">{typeof title === "string" ? title : "Oyna"}</Dialog.Description>
        )}
      </div>
      <Dialog.Close className="grid size-8 shrink-0 place-items-center rounded-lg text-fg-muted transition hover:bg-surface-2 hover:text-fg" aria-label="Yopish">
        <X className="size-4" />
      </Dialog.Close>
    </div>
  );
}

function Overlay() {
  return (
    <Dialog.Overlay asChild forceMount>
      <motion.div
        className="fixed inset-0 z-50 bg-[oklch(10%_0.03_268/55%)] backdrop-blur-sm"
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
      />
    </Dialog.Overlay>
  );
}

/** Markazdagi oyna. */
export function Modal({ open, onOpenChange, title, description, children, footer, className }: BaseProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open ? (
          <Dialog.Portal forceMount>
            <Overlay />
            <div className="pointer-events-none fixed inset-0 z-50 grid place-items-center p-3 sm:p-6">
              <Dialog.Content asChild forceMount>
                <motion.div
                  className={cn(
                    "pointer-events-auto flex max-h-[92dvh] w-full max-w-lg flex-col overflow-hidden rounded-2xl border bg-surface shadow-pop",
                    className,
                  )}
                  initial={{ opacity: 0, y: 24, scale: 0.96, rotateX: 8 }}
                  animate={{ opacity: 1, y: 0, scale: 1, rotateX: 0 }}
                  exit={{ opacity: 0, y: 12, scale: 0.97 }}
                  transition={{ type: "spring", stiffness: 380, damping: 32 }}
                  style={{ transformPerspective: 1200 }}
                >
                  <Header title={title} description={description} />
                  <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
                  {footer ? <div className="flex justify-end gap-2 border-t bg-surface-2/50 px-6 py-3">{footer}</div> : null}
                </motion.div>
              </Dialog.Content>
            </div>
          </Dialog.Portal>
        ) : null}
      </AnimatePresence>
    </Dialog.Root>
  );
}

/** O'ngdan chiqadigan panel (mobil'da pastdan). */
export function Sheet({ open, onOpenChange, title, description, children, footer, className }: BaseProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <AnimatePresence>
        {open ? (
          <Dialog.Portal forceMount>
            <Overlay />
            <Dialog.Content asChild forceMount>
              <motion.div
                className={cn(
                  "fixed inset-x-0 bottom-0 z-50 flex max-h-[94dvh] flex-col overflow-hidden rounded-t-2xl border bg-surface shadow-pop",
                  "sm:inset-y-3 sm:right-3 sm:left-auto sm:max-h-none sm:w-[min(760px,calc(100vw-1.5rem))] sm:rounded-2xl",
                  className,
                )}
                initial={{ opacity: 0, x: 40 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 40 }}
                transition={{ type: "spring", stiffness: 340, damping: 34 }}
              >
                <Header title={title} description={description} />
                <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
                {footer ? <div className="flex justify-end gap-2 border-t bg-surface-2/50 px-6 py-3">{footer}</div> : null}
              </motion.div>
            </Dialog.Content>
          </Dialog.Portal>
        ) : null}
      </AnimatePresence>
    </Dialog.Root>
  );
}
