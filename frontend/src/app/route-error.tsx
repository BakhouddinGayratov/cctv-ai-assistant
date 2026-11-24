import { useEffect } from "react";
import { useRouteError } from "react-router";
import { Button } from "@/components/ui/button";

const RELOAD_KEY = "cctv-chunk-reload";

function reloadOnce() {
  try {
    if (Date.now() - Number(sessionStorage.getItem(RELOAD_KEY) ?? 0) < 20_000) return;
    sessionStorage.setItem(RELOAD_KEY, String(Date.now()));
  } catch {
    /* ignore */
  }
  location.reload();
}

/** Sahifa eski build fayllarini so'rasa yoki server o'chiq bo'lsa, server javob berishi bilan o'zi yangilanadi. */
export function RouteError() {
  const error = useRouteError();
  const message = String((error as Error | null)?.message ?? error);
  const stale = /dynamically imported module|module script failed|Importing a module|Failed to fetch/i.test(message);

  useEffect(() => {
    if (!stale) return;
    const check = () => void fetch("/", { cache: "no-store" }).then((r) => { if (r.ok) reloadOnce(); }, () => undefined);
    check();
    const timer = window.setInterval(check, 3000);
    return () => window.clearInterval(timer);
  }, [stale]);

  return (
    <div className="grid min-h-[50dvh] place-items-center p-6 text-center">
      <div className="space-y-3">
        <p className="text-sm font-medium">{stale ? "Sahifa yuklanmadi" : "Sahifada xato yuz berdi"}</p>
        <p className="max-w-md text-xs text-fg-muted">
          {stale ? "Server bilan aloqa tiklanishi bilan sahifa o'zi ochiladi." : message}
        </p>
        <Button size="sm" onClick={() => location.reload()}>Qayta yuklash</Button>
      </div>
    </div>
  );
}
