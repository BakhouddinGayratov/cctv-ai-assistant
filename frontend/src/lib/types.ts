export interface Camera {
  channel: number;
  code_name: string;
  name: string;
  roles: CameraRole[];
}

export type CameraRole = "entrance" | "desk";

export interface AppConfig {
  nvr_ip: string;
  channels: number;
  cameras: Camera[];
  attendance_channels: number[];
  desk_channels: number[];
  monitor_window: string;
  default_work_start: string;
  default_work_end: string;
  version: string;
}

export interface ModelStatus {
  provider: "Gemini" | "Groq" | "—";
  model: string;
  used_at: string | null;
}

export type ChatMode = "live" | "playback" | "staff" | "general" | "job" | "search" | "agent";

export interface ChatResponse {
  query: string;
  answer: string;
  mode: ChatMode;
  channel: number | null;
  camera_name: string | null;
  snapshot_b64: string | null;
  frames_b64: string[] | null;
  video_url: string | null;
  time_start: string | null;
  time_end: string | null;
  job?: JobInfo | null;
  results?: SearchHit[] | null;
}

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
  ts: string;
}

export interface Employee {
  id: number;
  first_name: string;
  last_name: string;
  full_name: string;
  position: string;
  phone: string;
  work_start: string;
  work_end: string;
  active: boolean;
  desk_channel: number | null;
  desk_zone: [number, number, number, number] | null;
  room_id: number | null;
  samples: number;
  avatar: string | null;
}

export type EmployeeInput = Pick<
  Employee,
  "first_name" | "last_name" | "position" | "phone" | "work_start" | "work_end" | "active" | "desk_channel" | "room_id"
>;

export interface Room {
  id: number | null;
  name: string;
  kind: "work" | "meeting" | "rest" | "corridor" | "yard" | "blind";
  channels: number[];
  neighbors: number[];
}

export type TimeCategory = "ish" | "majlis" | "safar" | "qoshimcha" | "tushlik" | "tanaffus" | "dam" | "tashqarida" | "nomalum";

export interface NowPlace {
  name: string;
  kind: Room["kind"] | "out" | "away" | "unknown";
  conf: "seen" | "inferred" | "unknown";
  since: string;
}

export interface FaceSample {
  id: number;
  url: string;
  source: "upload" | "camera" | "sighting";
  created_at: string;
}

export interface UploadResult {
  results: { file: string; ok: boolean; reason?: string; note?: string | null }[];
  retro_identified: number;
}

export interface CapturedFace {
  index: number;
  crop_b64: string;
  name: string | null;
  similarity: number;
  too_small: boolean;
  size: string;
}

export interface CaptureResponse {
  token: string;
  image_b64: string;
  faces: CapturedFace[];
}

export interface UnknownSighting {
  id: number;
  ts: string;
  channel: number;
  camera: string;
  face_url: string;
  frame_url: string;
}

export type Direction = "IN" | "OUT";

export type AttendanceStatus = "ofisda" | "ketgan" | "kelmagan" | "chiqish qayd etilmagan";

export interface AttendanceRow {
  id: number;
  name: string;
  position: string;
  work_start: string;
  work_end: string;
  arrived: string | null;
  arrived_approx: boolean;
  left: string | null;
  status: AttendanceStatus;
  late_minutes: number;
  early_minutes: number;
  office_minutes: number;
  desk_minutes: number;
  confirmed_minutes: number;
  workplace: { channel: number; camera: string; mode: "room" | "zone" } | null;
  away_minutes: number | null;
  efficiency: number | null;
  time: Record<TimeCategory, number> | null;
  places: { name: string; kind: string; minutes: number; seen_minutes: number }[];
  now_place: NowPlace | null;
  room: string | null;
  away: { id: number; start: string; end: string; reason: string }[];
  passages: { ts: string; direction: Direction; channels: number[] }[];
  desk_timeline: { ts: string; present: boolean }[];
}

export interface AttendanceEvent {
  ts: string;
  employee_id: number | null;
  name: string;
  direction: Direction | null;
  channel: number;
  face_url: string;
  frame_url: string;
  sighting_id?: number;
}

export interface AttendanceSummary {
  total_employees: number;
  present: number;
  late: number;
  early_leave: number;
  total_office_hours: number;
  unknown_faces: number;
}

export interface AttendanceReport {
  date: string;
  summary: AttendanceSummary;
  employees: AttendanceRow[];
  events: AttendanceEvent[];
}

export interface WatcherStats {
  channel: number;
  state: string;
  connected: boolean;
  last_frame_at: string | null;
  frames_processed: number;
  skipped_static: number;
  faces_detected: number;
  sightings: number;
  resolution: string | null;
  last_error: string | null;
}

export interface WorkplaceNow {
  channel: number;
  present: boolean;
  method: "face" | "zone" | "seat" | "room";
  at: string;
}

export interface WorkersStatus {
  running: boolean;
  nvr_online: boolean;
  force_on: boolean;
  in_monitor_window: boolean;
  monitor_window: string;
  face_engine: { ready: boolean; error: string | null; samples: number; employees: number; threshold: number };
  watchers: WatcherStats[];
  desk: { state: string; last_check_at: string | null; channels: number[]; last_error: string | null; now: Record<string, WorkplaceNow> };
}

export interface ArchiveClip {
  url: string;
  camera_name: string;
  channel: number;
  start: string;
  end: string;
  seconds: number;
}

export interface ArchiveSnapshots {
  channel: number;
  camera_name: string;
  frames_b64: string[];
  found: number;
}

export type DeskCheckResult = Record<string, { employee_id: number; name: string; present: boolean; method: string }[]>;

// ---------------------------------------------------------------- Bosqich 2–5
export type AlertKind = "unknown_face" | "after_hours" | "camera_offline" | "agent" | "daily_summary" | "arrival" | "test";
export type Severity = "info" | "warning" | "critical";

export interface AlertItem {
  id: number;
  ts: string;
  kind: AlertKind;
  kind_label: string;
  severity: Severity;
  channel: number | null;
  employee_id: number | null;
  title: string;
  message: string;
  snapshot_url: string | null;
  clip_url: string | null;
  tts_url: string | null;
  acknowledged: boolean;
}

export interface AlertList {
  items: AlertItem[];
  unread: number;
}

export type LiveEvent = { type: "alert" | "alert_update"; alert: AlertItem };

export interface AppSettings {
  telegram_token: string;
  telegram_token_set: boolean;
  telegram_chat_id: string;
  telegram_configured: boolean;
  alert_unknown_face: boolean;
  alert_unknown_cooldown_min: number;
  alert_after_hours: boolean;
  security_cameras: number[];
  after_hours_start: string;
  after_hours_end: string;
  after_hours_weekends: boolean;
  after_hours_cooldown_min: number;
  alert_camera_offline: boolean;
  daily_summary: boolean;
  daily_summary_time: string;
  weekly_report: boolean;
  agent_enabled: boolean;
  agent_away_minutes: number;
  lunch_start: string;
  lunch_end: string;
  yard_max_min: number;
  blind_max_min: number;
  room_grace_min: number;
  announce_arrivals: boolean;
  alert_tts: boolean;
  tts_voice: string;
  indexer_enabled: boolean;
  indexer_interval_min: number;
}

export interface SystemInfo {
  security: {
    after_hours_now: boolean;
    watchers: { channel: number; state: string; connected: boolean; motion: number; last_frame_at: string | null; alerts: number }[];
  };
  scheduler: { id: string; next_run: string | null }[];
}

export interface AnalyticsDay {
  date: string;
  total_employees: number;
  present: number;
  late: number;
  early_leave: number;
  total_office_hours: number;
  unknown_faces: number;
  avg_efficiency: number | null;
  workday: boolean;
}

export interface AnalyticsEmployee {
  id: number;
  name: string;
  position: string;
  days_present: number;
  late_days: number;
  late_minutes: number;
  early_days: number;
  office_hours: number;
  desk_hours: number;
  avg_efficiency: number | null;
  avg_arrival: string | null;
}

export interface Analytics {
  from: string;
  to: string;
  days: AnalyticsDay[];
  employees: AnalyticsEmployee[];
  arrival_histogram: { hour: number; count: number }[];
  hourly_activity: { hour: number; minutes: number }[];
  cameras: { channel: number; name: string; sightings: number; active_minutes: number; avg_motion: number }[];
  alerts: Record<string, number>;
  totals: { workdays: number; attendance_rate: number; late_total: number; office_hours: number; unknown_faces: number };
}

export interface TimelineData {
  channel: number;
  date: string;
  camera: string;
  recordings: { start: string; end: string; type: "continuous" | "motion" | "event" }[] | null;
  recordings_available: boolean;
  activity: { minute: number; motion: number; people: number }[];
  sightings: { ts: string; name: string; known: boolean; face_url: string }[];
  alerts: AlertItem[];
  coverage: { start: string; end: string }[];
}

export interface JobInfo {
  id: string;
  kind: "clip" | "summary";
  title: string;
  status: "running" | "done" | "error";
  progress: number;
  message: string;
  result: { url: string; moments?: { ts: string; channel: number; label: string }[] } | null;
  elapsed: number;
  started_at: string;
}

export interface SearchHit {
  ts: string;
  channel: number;
  text: string;
  image: string | null;
}

export interface PtzInfo {
  channel: number;
  supported: boolean;
  presets: { id: number; name: string }[];
}
