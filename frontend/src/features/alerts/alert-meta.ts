import { BellRing, CircleAlert, Info, ScanFace, ShieldAlert, Sparkles, UserCheck, VideoOff, type LucideIcon } from "lucide-react";
import type { AlertKind, Severity } from "@/lib/types";

export const SEVERITY_STYLE: Record<Severity, { label: string; soft: string; dot: string; icon: LucideIcon; tone: "neutral" | "warning" | "critical" }> = {
  info: { label: "Ma'lumot", soft: "bg-accent-soft text-accent", dot: "bg-accent", icon: Info, tone: "neutral" },
  warning: { label: "Diqqat", soft: "bg-warning-soft text-warning", dot: "bg-warning", icon: CircleAlert, tone: "warning" },
  critical: { label: "Jiddiy", soft: "bg-critical-soft text-critical", dot: "bg-critical", icon: ShieldAlert, tone: "critical" },
};

export const KIND_META: Record<AlertKind, { label: string; icon: LucideIcon }> = {
  unknown_face: { label: "Notanish odam", icon: ScanFace },
  after_hours: { label: "Ish vaqtidan tashqari", icon: ShieldAlert },
  camera_offline: { label: "Kamera aloqasi", icon: VideoOff },
  agent: { label: "AI agent", icon: Sparkles },
  daily_summary: { label: "Kunlik xulosa", icon: BellRing },
  arrival: { label: "Kelish", icon: UserCheck },
  test: { label: "Sinov", icon: Info },
};
