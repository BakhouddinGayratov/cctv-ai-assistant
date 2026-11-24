import {
  BrainCircuit, CalendarCheck, Cctv, ChartColumnBig, Ellipsis, Film, LayoutGrid, LogOut, Moon, ScanFace, Server, Settings2,
  ShieldAlert, Sparkles, Sun, UserRoundCheck, UsersRound, X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { lazy, Suspense, useEffect, useState } from "react";
import { AlertStream } from "@/features/alerts/alert-stream";
import { NotificationBell } from "@/features/alerts/notification-bell";
import { NavLink, useLocation, useNavigation, useOutlet } from "react-router";
import { StatusDot } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { useRole } from "@/lib/auth";
import { useModelStatus, useWorkers } from "@/lib/queries";
import { cn } from "@/lib/utils";
import { ErrorBoundary } from "./error-boundary";
import { useTheme } from "./theme";

const NAV = [
  { to: "/", label: "Bugun", icon: CalendarCheck, title: "Bugun", subtitle: "Kim keldi, kim joyida, nima bo'ldi", boss: true },
  { to: "/grid", label: "Kameralar", icon: LayoutGrid, title: "Kameralar", subtitle: "Katakni bosing — kattalashadi", boss: true },
  { to: "/archive", label: "Arxiv", icon: Film, title: "Arxiv", subtitle: "Sana, vaqt va qidiruv", boss: true },
  { to: "/analytics", label: "Hisobot", icon: ChartColumnBig, title: "Hisobot", subtitle: "Davomat grafiklari, Excel va PDF", boss: true },
  { to: "/monitor", label: "Kuzatuv", icon: Cctv, title: "Jonli kuzatuv", subtitle: "Kameralar, 3D xarita va AI yordamchi", boss: false },
  { to: "/attendance", label: "Davomat", icon: UserRoundCheck, title: "Davomat", subtitle: "Yuz tanish orqali avtomatik kelish-ketish", boss: false },
  { to: "/employees", label: "Xodimlar", icon: UsersRound, title: "Xodimlar", subtitle: "Yuz namunalari, ish joylari, notanish yuzlar", boss: false },
  { to: "/alerts", label: "Hodisalar", icon: ShieldAlert, title: "Hodisalar", subtitle: "Ogohlantirishlar va AI agent xabarlari", boss: false },
  { to: "/settings", label: "Sozlamalar", icon: Settings2, title: "Sozlamalar", subtitle: "Ogohlantirishlar, hisobotlar, agent", boss: false },
] as const;

function Brand({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <div className="relative grid size-10 shrink-0 place-items-center rounded-xl bg-brand-gradient shadow-glow">
        <ScanFace className="size-5 text-white" strokeWidth={2.2} />
      </div>
      {compact ? null : (
        <div className="leading-tight">
          <p className="text-[15px] font-semibold tracking-tight">CCTV AI</p>
          <p className="text-[11px] text-fg-subtle">Xodimlar nazorati</p>
        </div>
      )}
    </div>
  );
}

function ThemeToggle({ className }: { className?: string }) {
  const { theme, toggle } = useTheme();
  return (
    <button
      onClick={toggle}
      aria-label={theme === "dark" ? "Yorug' mavzuga o'tish" : "Qorong'i mavzuga o'tish"}
      className={cn("relative grid size-9 place-items-center overflow-hidden rounded-lg text-fg-muted transition hover:bg-surface-2 hover:text-fg", className)}
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={theme}
          initial={{ y: -16, opacity: 0, rotate: -90 }}
          animate={{ y: 0, opacity: 1, rotate: 0 }}
          exit={{ y: 16, opacity: 0, rotate: 90 }}
          transition={{ duration: 0.25 }}
        >
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}

function SystemCard() {
  const workers = useWorkers();
  const model = useModelStatus(true);
  const w = workers.data;
  const rows = [
    {
      icon: Server,
      label: "NVR",
      value: w ? (w.nvr_online ? "ulangan" : "ulanmagan") : "…",
      tone: w?.nvr_online ? "good" : "critical",
    },
    {
      icon: ScanFace,
      label: "Yuz tanish",
      value: w ? (w.face_engine.ready ? `${w.face_engine.employees} xodim` : "tayyor emas") : "…",
      tone: w?.face_engine.ready ? "good" : "warning",
    },
    {
      icon: BrainCircuit,
      label: "AI",
      value: model.data?.provider && model.data.provider !== "—" ? model.data.provider : "kutilmoqda",
      tone: model.data?.provider === "Gemini" || model.data?.provider === "Groq" ? "good" : "neutral",
    },
  ] as const;
  return (
    <div className="rounded-xl border bg-surface-2/60 p-3">
      <p className="mb-2 text-[10px] font-semibold tracking-[0.12em] text-fg-subtle uppercase">Tizim holati</p>
      <ul className="space-y-2">
        {rows.map((r) => (
          <li key={r.label} className="flex items-center gap-2 text-xs">
            <r.icon className="size-3.5 text-fg-subtle" />
            <span className="text-fg-muted">{r.label}</span>
            <span className="ml-auto flex items-center gap-1.5 font-medium">
              <StatusDot tone={r.tone} pulse={r.tone === "good"} />
              {r.value}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function logout() {
  void api.logout().finally(() => location.assign("/login"));
}

function Sidebar() {
  const admin = useRole() === "admin";
  return (
    <aside className="glass sticky top-0 hidden h-dvh w-[76px] shrink-0 flex-col border-r px-3 py-5 lg:flex xl:w-64 xl:px-4">
      <div className="px-1.5 xl:px-2">
        <div className="xl:hidden">
          <Brand compact />
        </div>
        <div className="hidden xl:block">
          <Brand />
        </div>
      </div>
      <nav aria-label="Asosiy menyu" className="mt-8 flex flex-col gap-1">
        {NAV.filter((n) => admin || n.boss).map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === "/"} className="group relative">
            {({ isActive }) => (
              <Tooltip content={item.label} side="right">
                <span
                  className={cn(
                    "relative flex h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors",
                    isActive ? "text-fg" : "text-fg-muted hover:bg-surface-2 hover:text-fg",
                  )}
                >
                  {isActive ? (
                    <motion.span
                      layoutId="nav-active"
                      className="absolute inset-0 rounded-xl border border-brand/25 bg-brand-soft"
                      transition={{ type: "spring", stiffness: 480, damping: 36 }}
                    />
                  ) : null}
                  <item.icon className={cn("relative size-[18px] shrink-0", isActive && "text-brand")} />
                  <span className="relative hidden xl:inline">{item.label}</span>
                </span>
              </Tooltip>
            )}
          </NavLink>
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-3">
        {admin ? (
          <div className="hidden xl:block">
            <SystemCard />
          </div>
        ) : null}
        <ThemeToggle className="self-center xl:self-start" />
      </div>
    </aside>
  );
}

function MobileNav() {
  const [more, setMore] = useState(false);
  const { pathname } = useLocation();
  const secondary = useRole() === "admin" ? NAV.filter((n) => !n.boss) : [];
  const inSecondary = secondary.some((n) => pathname.startsWith(n.to));
  return (
    <>
      <AnimatePresence>
        {more ? (
          <>
            <motion.div className="fixed inset-0 z-40 bg-black/40 lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={() => setMore(false)} />
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: 20 }}
              className="glass fixed inset-x-3 bottom-24 z-50 grid grid-cols-2 gap-1.5 rounded-2xl border p-2 shadow-pop lg:hidden"
            >
              {secondary.map((item) => (
                <NavLink key={item.to} to={item.to} onClick={() => setMore(false)}
                  className={({ isActive }) => cn("flex items-center gap-2.5 rounded-xl px-3 py-3 text-sm font-medium", isActive ? "bg-brand-soft text-brand" : "text-fg-muted hover:bg-surface-2")}>
                  <item.icon className="size-5" /> {item.label}
                </NavLink>
              ))}
            </motion.div>
          </>
        ) : null}
      </AnimatePresence>
      <nav
        aria-label="Asosiy menyu"
        className="glass fixed inset-x-3 bottom-3 z-40 flex justify-around rounded-2xl border p-1.5 shadow-pop lg:hidden"
        style={{ paddingBottom: "max(0.375rem, env(safe-area-inset-bottom))" }}
      >
        {NAV.filter((n) => n.boss).map((item) => (
          <NavLink key={item.to} to={item.to} end={item.to === "/"} className="relative flex-1" onClick={() => setMore(false)}>
            {({ isActive }) => (
              <span className={cn("relative flex flex-col items-center gap-0.5 rounded-xl py-2 text-[11px] font-medium", isActive ? "text-brand" : "text-fg-muted")}>
                {isActive ? (
                  <motion.span layoutId="mnav-active" className="absolute inset-0 rounded-xl bg-brand-soft" transition={{ type: "spring", stiffness: 480, damping: 36 }} />
                ) : null}
                <item.icon className="relative size-5" />
                <span className="relative">{item.label}</span>
              </span>
            )}
          </NavLink>
        ))}
        {secondary.length ? <button onClick={() => setMore((m) => !m)} aria-expanded={more} className="relative flex-1">
          <span className={cn("relative flex flex-col items-center gap-0.5 rounded-xl py-2 text-[11px] font-medium", inSecondary || more ? "text-brand" : "text-fg-muted")}>
            {inSecondary ? <motion.span layoutId="mnav-active" className="absolute inset-0 rounded-xl bg-brand-soft" /> : null}
            <Ellipsis className="relative size-5" />
            <span className="relative">Ko'proq</span>
          </span>
        </button> : null}
      </nav>
    </>
  );
}

function TopBar() {
  const { pathname } = useLocation();
  const item = NAV.find((n) => (n.to === "/" ? pathname === "/" : pathname.startsWith(n.to))) ?? NAV[0];
  const admin = useRole() === "admin";
  const model = useModelStatus(admin);
  const workers = useWorkers();
  const provider = model.data?.provider;
  return (
    <header className="glass sticky top-0 z-30 border-b">
      <div className="mx-auto flex h-16 max-w-[1720px] items-center gap-3 px-4 sm:px-6">
        <div className="lg:hidden">
          <Brand compact />
        </div>
        <AnimatePresence mode="wait" initial={false}>
          <motion.div
            key={item.to}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.2 }}
            className="min-w-0"
          >
            <h1 className="truncate text-base font-semibold tracking-tight sm:text-lg">{item.title}</h1>
            <p className="hidden truncate text-xs text-fg-muted sm:block">{item.subtitle}</p>
          </motion.div>
        </AnimatePresence>
        <div className="ml-auto flex items-center gap-2">
          {admin ? <Tooltip content={model.data?.used_at ? `Oxirgi javob: ${model.data.used_at.slice(11, 19)} (UTC)` : "Hali javob berilmagan"}>
            <div
              className={cn(
                "hidden items-center gap-2 rounded-xl border px-3 py-1.5 sm:flex",
                provider === "Gemini" && "border-accent/30 bg-accent-soft",
                provider === "Groq" && "border-warning/30 bg-warning-soft",
              )}
            >
              <BrainCircuit className={cn("size-4", provider === "Gemini" ? "text-accent" : provider === "Groq" ? "text-warning" : "text-fg-subtle")} />
              <div className="leading-tight">
                <p className="text-[9px] font-semibold tracking-[0.14em] text-fg-subtle uppercase">Faol AI model</p>
                <p className="max-w-[210px] truncate font-mono text-[11px]">
                  <span className="font-semibold">{provider && provider !== "—" ? provider : "—"}</span>
                  <span className="text-fg-muted"> · {model.data?.model ?? "kutilmoqda"}</span>
                </p>
              </div>
            </div>
          </Tooltip> : null}
          <div className="flex items-center gap-2 rounded-xl border px-3 py-2 text-xs">
            <StatusDot tone={workers.data?.nvr_online ? "good" : "critical"} pulse={workers.data?.nvr_online} />
            <span className="font-medium">Kameralar</span>
            <span className="hidden text-fg-muted md:inline">{workers.data?.nvr_online ? "ulangan" : "ulanmagan"}</span>
          </div>
          <NotificationBell />
          <ThemeToggle className="lg:hidden" />
          <Tooltip content="Chiqish">
            <button onClick={logout} aria-label="Tizimdan chiqish" className="grid size-9 place-items-center rounded-lg border text-fg-muted transition hover:bg-surface-2 hover:text-fg">
              <LogOut className="size-4" />
            </button>
          </Tooltip>
        </div>
      </div>
    </header>
  );
}

function RouteProgress() {
  const nav = useNavigation();
  return (
    <AnimatePresence>
      {nav.state === "loading" ? (
        <motion.div
          className="fixed inset-x-0 top-0 z-50 h-0.5 origin-left bg-brand-gradient"
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 0.8 }}
          exit={{ scaleX: 1, opacity: 0 }}
          transition={{ duration: 0.6 }}
        />
      ) : null}
    </AnimatePresence>
  );
}

const ChatPanel = lazy(() => import("@/features/chat/chat-panel").then((m) => ({ default: m.ChatPanel })));
const noop = () => undefined;

function ChatButton() {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      {open ? (
        <div className="fixed inset-x-3 bottom-40 z-40 h-[min(620px,calc(100dvh-12rem))] lg:inset-x-auto lg:right-6 lg:bottom-24 lg:h-[min(620px,calc(100dvh-8rem))] lg:w-[420px]">
          <Suspense fallback={null}>
            <ChatPanel className="h-full shadow-pop" context={null} onClearContext={noop} />
          </Suspense>
        </div>
      ) : null}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "AI yordamchini yopish" : "AI yordamchini ochish"}
        aria-expanded={open}
        className="fixed right-4 bottom-24 z-40 grid size-13 place-items-center rounded-full bg-brand-gradient text-white shadow-glow lg:right-6 lg:bottom-6"
      >
        {open ? <X className="size-5" /> : <Sparkles className="size-5" />}
      </button>
    </>
  );
}

export function AppShell() {
  const { pathname } = useLocation();
  const outlet = useOutlet();
  return (
    <div className="flex min-h-dvh">
      <div className="app-backdrop" />
      <AlertStream />
      <RouteProgress />
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="mx-auto w-full max-w-[1720px] flex-1 px-4 pt-5 pb-28 sm:px-6 lg:pb-8">
          <ErrorBoundary>
            <Suspense fallback={null}>
              <AnimatePresence mode="wait" initial={false}>
                <motion.div
                  key={pathname}
                  initial={{ opacity: 0, y: 14 }}
                  animate={{ opacity: 1, y: 0, transitionEnd: { transform: "none" } }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                >
                  {outlet}
                </motion.div>
              </AnimatePresence>
            </Suspense>
          </ErrorBoundary>
        </main>
      </div>
      <MobileNav />
      {pathname === "/monitor" ? null : <ChatButton />}
    </div>
  );
}
