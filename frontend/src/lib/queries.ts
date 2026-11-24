import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, ext } from "./api";
import type { EmployeeInput } from "./types";
import { shiftDate, todayIso } from "./utils";

export const keys = {
  config: ["config"] as const,
  model: ["model"] as const,
  workers: ["workers"] as const,
  attendance: (date: string) => ["attendance", date] as const,
  employees: ["employees"] as const,
  faces: (id: number) => ["faces", id] as const,
  unknown: ["unknown"] as const,
  chat: ["chat"] as const,
};

export const useConfig = () => useQuery({ queryKey: keys.config, queryFn: api.config, staleTime: Infinity });

export const useModelStatus = (enabled: boolean) =>
  useQuery({ queryKey: keys.model, queryFn: api.modelStatus, refetchInterval: 15_000, enabled });

export const useWorkers = () => useQuery({ queryKey: keys.workers, queryFn: api.workers, refetchInterval: 10_000 });

export const useAttendance = (date: string) =>
  useQuery({
    queryKey: keys.attendance(date),
    queryFn: () => api.attendance(date),
    refetchInterval: date === todayIso() ? 20_000 : false,
    placeholderData: (prev) => prev,
  });

/** Oxirgi 7 kun davomati — parallel so'rovlar (waterfall yo'q). */
export function useWeekAttendance(endDay: string) {
  const days = Array.from({ length: 7 }, (_, i) => shiftDate(endDay, i - 6));
  return useQueries({
    queries: days.map((d) => ({
      queryKey: keys.attendance(d),
      queryFn: () => api.attendance(d),
      staleTime: d === todayIso() ? 20_000 : 5 * 60_000,
    })),
    combine: (results) => ({
      days,
      reports: results.map((r) => r.data),
      isLoading: results.some((r) => r.isLoading),
    }),
  });
}

export const useEmployees = () => useQuery({ queryKey: keys.employees, queryFn: api.employees });

export const useFaces = (id: number | null) =>
  useQuery({ queryKey: keys.faces(id ?? 0), queryFn: () => api.faces(id as number), enabled: id != null });

export const useUnknown = () => useQuery({ queryKey: keys.unknown, queryFn: api.unknownSightings, refetchInterval: 30_000 });

export const useChatHistory = () => useQuery({ queryKey: keys.chat, queryFn: api.chatHistory, staleTime: Infinity });

/** Yuz/xodim o'zgarganda bog'liq kesh qismlarini yangilash. */
export function useInvalidateStaff() {
  const qc = useQueryClient();
  return () =>
    Promise.all([
      qc.invalidateQueries({ queryKey: keys.employees }),
      qc.invalidateQueries({ queryKey: keys.unknown }),
      qc.invalidateQueries({ queryKey: keys.workers }),
      qc.invalidateQueries({ queryKey: ["attendance"] }),
    ]);
}

export function useSaveEmployee() {
  const invalidate = useInvalidateStaff();
  return useMutation({
    mutationFn: ({ id, body }: { id: number | null; body: EmployeeInput }) =>
      id == null ? api.createEmployee(body) : api.updateEmployee(id, body),
    onSuccess: (_e, v) => {
      toast.success(v.id == null ? "Xodim qo'shildi" : "O'zgarishlar saqlandi");
      void invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useDeleteEmployee() {
  const invalidate = useInvalidateStaff();
  return useMutation({
    mutationFn: (id: number) => api.deleteEmployee(id),
    onSuccess: () => {
      toast.success("Xodim o'chirildi");
      void invalidate();
    },
    onError: (e: Error) => toast.error(e.message),
  });
}

// ---------------------------------------------------------------- Bosqich 2–5
export const extKeys = {
  alerts: (f: object) => ["alerts", f] as const,
  settings: ["settings"] as const,
  system: ["system"] as const,
  analytics: (from: string, to: string) => ["analytics", from, to] as const,
  timeline: (ch: number, day: string) => ["timeline", ch, day] as const,
  ptz: (ch: number) => ["ptz", ch] as const,
  jobs: ["jobs"] as const,
};

export const useAlerts = (f: { from?: string; to?: string; kind?: string; unacked?: boolean } = {}) =>
  useQuery({ queryKey: extKeys.alerts(f), queryFn: () => ext.alerts(f), refetchInterval: 60_000 });

export const useSettings = () => useQuery({ queryKey: extKeys.settings, queryFn: ext.settings });
export const useSystem = () => useQuery({ queryKey: extKeys.system, queryFn: ext.system, refetchInterval: 15_000 });
export const useAnalytics = (from: string, to: string) =>
  useQuery({ queryKey: extKeys.analytics(from, to), queryFn: () => ext.analytics(from, to), placeholderData: (p) => p });
export const useTimeline = (ch: number, day: string) =>
  useQuery({ queryKey: extKeys.timeline(ch, day), queryFn: () => ext.timeline(ch, day), refetchInterval: day === todayIso() ? 60_000 : false });
export const usePtz = (ch: number | null) =>
  useQuery({ queryKey: extKeys.ptz(ch ?? 0), queryFn: () => ext.ptz(ch as number), enabled: ch != null, staleTime: 10 * 60_000, retry: false });

/** Fon vazifasini tugaguncha kuzatadi. */
export const useJob = (id: string | null) =>
  useQuery({
    queryKey: ["job", id],
    queryFn: () => ext.job(id as string),
    enabled: id != null,
    refetchInterval: (q) => (q.state.data && q.state.data.status !== "running" ? false : 1500),
  });
export const useJobs = () => useQuery({ queryKey: extKeys.jobs, queryFn: ext.jobs, refetchInterval: 3000 });
