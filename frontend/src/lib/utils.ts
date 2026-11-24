import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

const pad = (n: number) => String(n).padStart(2, "0");

/** Mahalliy vaqt bo'yicha ISO (UTC'ga o'tkazmasdan) — backend mahalliy vaqt bilan ishlaydi. */
export function localIso(d: Date, withSeconds = true): string {
  const base = `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return withSeconds ? `${base}:${pad(d.getSeconds())}` : base;
}

export const todayIso = () => localIso(new Date()).slice(0, 10);

export function shiftDate(day: string, delta: number): string {
  const d = new Date(`${day}T12:00:00`);
  d.setDate(d.getDate() + delta);
  return localIso(d).slice(0, 10);
}

export const hhmm = (iso: string | null | undefined) => (iso ? iso.slice(11, 16) : "—");

export const channelLabel = (ch: number) => `CH-${pad(ch)}`;

export function formatMinutes(m: number | null | undefined): string {
  if (m == null) return "—";
  const v = Math.round(m);
  if (v < 60) return `${v} daq`;
  return `${Math.floor(v / 60)} s ${v % 60} daq`;
}

const WEEKDAYS = ["Yakshanba", "Dushanba", "Seshanba", "Chorshanba", "Payshanba", "Juma", "Shanba"];
const MONTHS = ["yanvar", "fevral", "mart", "aprel", "may", "iyun", "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr"];

export function formatDayLong(day: string): string {
  const d = new Date(`${day}T12:00:00`);
  return `${d.getDate()}-${MONTHS[d.getMonth()]}, ${WEEKDAYS[d.getDay()]}`;
}

export const weekdayShort = (day: string) => (WEEKDAYS[new Date(`${day}T12:00:00`).getDay()] ?? "").slice(0, 2);

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

/** Soat (kasr) — kun chizig'i uchun. */
export function hourOf(iso: string): number {
  const h = Number(iso.slice(11, 13));
  const m = Number(iso.slice(14, 16));
  return h + m / 60;
}

export function parseWindow(win: string): [number, number] {
  const parts = win.split(/[–-]/).map((t) => {
    const [h = "0", m = "0"] = t.trim().split(":");
    return Number(h) + Number(m) / 60;
  });
  return [parts[0] ?? 7.5, parts[1] ?? 20];
}
