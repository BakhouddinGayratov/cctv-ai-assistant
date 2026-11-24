import type {
  AlertItem, AlertList, Analytics, AppConfig, AppSettings, ArchiveClip, ArchiveSnapshots, AttendanceReport,
  CaptureResponse, ChatResponse, ChatTurn, DeskCheckResult, Employee, EmployeeInput, FaceSample, JobInfo,
  ModelStatus, PtzInfo, Room, SearchHit, SystemInfo, TimelineData, UnknownSighting, UploadResult, WorkersStatus,
} from "./types";

import type { Role } from "./auth";

export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

type Json = Record<string, unknown> | unknown[];

async function request<T>(url: string, init: RequestInit & { json?: Json } = {}): Promise<T> {
  const { json, ...rest } = init;
  const opts: RequestInit = { cache: "no-store", ...rest };
  if (json !== undefined) {
    opts.method ??= "POST";
    opts.headers = { "Content-Type": "application/json", ...opts.headers };
    opts.body = JSON.stringify(json);
  }
  const res = await fetch(url, opts);
  const data: unknown = await res.json().catch(() => null);
  if (res.status === 401 && !url.startsWith("/api/auth/")) location.assign("/login");
  if (!res.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    throw new ApiError(typeof detail === "string" ? detail : `Server xatosi (${res.status})`, res.status);
  }
  return data as T;
}

const q = (params: Record<string, string | number | boolean>) =>
  new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  me: () => request<{ role: Role }>("/api/auth/me"),
  login: (login: string, password: string) => request<{ role: Role }>("/api/auth/login", { json: { login, password } }),
  logout: () => request<{ status: string }>("/api/auth/logout", { method: "POST" }),

  config: () => request<AppConfig>("/api/config"),
  modelStatus: () => request<ModelStatus>("/api/model/status"),
  workers: () => request<WorkersStatus>("/api/workers/status"),
  forceWorkers: (on: boolean) => request<WorkersStatus>("/api/workers/force", { json: { on } }),
  deskCheckNow: () => request<DeskCheckResult>("/api/desk/check-now", { method: "POST" }),

  chat: (query: string, forceChannel: number | null) =>
    request<ChatResponse>("/api/chat", {
      json: { query, session_id: "default", force_channel: forceChannel, want_clip: false, want_gallery: true },
    }),
  chatHistory: () => request<ChatTurn[]>("/api/chat/history?session_id=default&limit=40"),
  clearChat: () => request<{ status: string }>("/api/chat/history?session_id=default", { method: "DELETE" }),

  stopStream: (prefix = "main") => request<{ status: string }>(`/api/stream/stop?prefix=${prefix}`, { method: "POST" }),
  archiveSnapshots: (channel: number, start: string, end: string, count = 4) =>
    request<ArchiveSnapshots>(`/api/archive/quick-snapshots?${q({ channel, start_iso: start, end_iso: end, count })}`),
  archiveClip: (channel: number, start: string, end: string, signal?: AbortSignal) =>
    request<ArchiveClip>(`/api/archive/clip?${q({ channel, start_iso: start, end_iso: end, max_seconds: 30 })}`, {
      method: "POST",
      signal,
    }),

  attendance: (date: string) => request<AttendanceReport>(`/api/attendance?${q({ date })}`),

  employees: () => request<Employee[]>("/api/employees"),
  createEmployee: (body: EmployeeInput) => request<Employee>("/api/employees", { json: body }),
  updateEmployee: (id: number, body: EmployeeInput) => request<Employee>(`/api/employees/${id}`, { method: "PUT", json: body }),
  deleteEmployee: (id: number) => request<{ status: string }>(`/api/employees/${id}`, { method: "DELETE" }),
  setDesk: (id: number, desk_channel: number | null, zone: number[] | null) =>
    request<{ status: string }>(`/api/employees/${id}/desk`, { method: "PUT", json: { desk_channel, zone } }),

  faces: (id: number) => request<FaceSample[]>(`/api/employees/${id}/faces`),
  uploadFaces: (id: number, files: File[]) => {
    const fd = new FormData();
    for (const f of files) fd.append("files", f);
    return request<UploadResult>(`/api/employees/${id}/faces/upload`, { method: "POST", body: fd });
  },
  captureFaces: (channel: number) => request<CaptureResponse>(`/api/faces/capture?${q({ channel })}`, { method: "POST" }),
  faceFromCapture: (id: number, token: string, index: number) =>
    request<{ id: number; retro_identified: number }>(`/api/employees/${id}/faces/from-capture`, { json: { token, index } }),
  deleteFace: (sampleId: number) => request<{ status: string }>(`/api/faces/${sampleId}`, { method: "DELETE" }),

  unknownSightings: () => request<UnknownSighting[]>("/api/sightings/unknown?days=7&limit=64"),
  assignSighting: (id: number, employee_id: number) =>
    request<{ status: string; retro_identified: number }>(`/api/sightings/${id}/assign`, { json: { employee_id } }),
  deleteSighting: (id: number) => request<{ status: string }>(`/api/sightings/${id}`, { method: "DELETE" }),
};

export const ext = {
  alerts: (p: { from?: string; to?: string; kind?: string; unacked?: boolean } = {}) =>
    request<AlertList>(`/api/alerts?${q({ ...(p.from ? { date_from: p.from } : {}), ...(p.to ? { date_to: p.to } : {}),
      ...(p.kind ? { kind: p.kind } : {}), unacked: p.unacked ?? false })}`),
  ackAlert: (id: number) => request<{ status: string }>(`/api/alerts/${id}/ack`, { method: "POST" }),
  ackAll: () => request<{ status: string }>("/api/alerts/ack-all", { method: "POST" }),
  testAlert: () => request<AlertItem>("/api/alerts/test", { method: "POST" }),

  settings: () => request<AppSettings>("/api/settings"),
  saveSettings: (body: Partial<AppSettings>) => request<AppSettings>("/api/settings", { method: "PUT", json: body }),
  system: () => request<SystemInfo>("/api/system"),

  analytics: (from: string, to: string) => request<Analytics>(`/api/analytics?${q({ date_from: from, date_to: to })}`),
  reportUrl: (fmt: "xlsx" | "pdf", from: string, to: string) => `/api/reports/attendance.${fmt}?${q({ date_from: from, date_to: to })}`,
  dailySummary: (day?: string) => request<AlertItem>(`/api/reports/daily-summary?${q({ ...(day ? { day } : {}), notify: false })}`, { method: "POST" }),
  weeklyReport: () => request<{ xlsx: string; pdf: string; from: string; to: string }>("/api/reports/weekly", { method: "POST" }),
  heatmapChannels: (day: string) => request<{ channels: number[] }>(`/api/heatmap?${q({ day })}`),
  heatmapUrl: (ch: number, day: string) => `/api/heatmap/${ch}?${q({ day, t: Date.now() })}`,

  timeline: (channel: number, day: string) => request<TimelineData>(`/api/timeline?${q({ channel, day })}`),
  ptz: (ch: number) => request<PtzInfo>(`/api/ptz/${ch}`),
  ptzMove: (ch: number, pan: number, tilt: number, zoom: number) => request<{ status: string }>(`/api/ptz/${ch}/move`, { json: { pan, tilt, zoom } }),
  ptzStop: (ch: number) => request<{ status: string }>(`/api/ptz/${ch}/stop`, { method: "POST" }),
  ptzPreset: (ch: number, id: number) => request<{ status: string }>(`/api/ptz/${ch}/preset/${id}`, { method: "POST" }),

  jobs: () => request<JobInfo[]>("/api/jobs"),
  job: (id: string) => request<JobInfo>(`/api/jobs/${id}`),
  clipJob: (channel: number, start: string, seconds = 30) => request<JobInfo>("/api/jobs/clip", { json: { channel, start, seconds } }),
  summaryJob: (day: string, channel?: number | null) => request<JobInfo>("/api/jobs/summary", { json: { day, channel: channel ?? null } }),

  search: (query: string, days = 7, channel?: number | null) =>
    request<{ answer: string; results: SearchHit[] }>(`/api/search?${q({ q: query, days, ...(channel ? { channel } : {}) })}`),
  indexStats: () => request<{ frames: number; last: string | null }>("/api/index/stats"),
  runIndex: () => request<{ written: number }>("/api/index/run", { method: "POST" }),
  rooms: () => request<{ rooms: Room[]; kinds: Record<Room["kind"], string> }>("/api/rooms"),
  saveRooms: (rooms: Room[]) => request<{ rooms: Room[]; kinds: Record<Room["kind"], string> }>("/api/rooms", { method: "PUT", json: { rooms } }),
  addAway: (body: { employee_id: number; start: string; end: string; reason: string }) => request<{ id: number }>("/api/presence/away", { json: body }),
  deleteAway: (id: number) => request<{ status: string }>(`/api/presence/away/${id}`, { method: "DELETE" }),
  runAgent: () => request<{ messages: string[] }>("/api/agent/run", { method: "POST" }),
};

export const streamUrl = (channel: number) => `/api/stream/${channel}?faces=1&t=${Date.now()}`;
export const snapshotUrl = (channel: number, hq = false) => `/api/snapshot/${channel}?hq=${hq ? 1 : 0}&t=${Date.now()}`;
export const b64Jpeg = (b64: string) => `data:image/jpeg;base64,${b64}`;
