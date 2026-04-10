import axios, { AxiosInstance } from 'axios';
import { resolveApiBaseUrl } from './baseUrl';

const API_URL = resolveApiBaseUrl({
  envApiUrl: process.env.EXPO_PUBLIC_API_URL,
  isWeb: typeof window !== 'undefined',
  windowOrigin: typeof window !== 'undefined' ? window.location.origin : undefined,
});

let sessionId: string | null = null;

const SESSION_ID_KEY = 'rf2_client_session_id';
const SESSION_ID_COOKIE = 'rf2_session_id';

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;

  const prefix = `${name}=`;
  const cookie = document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));

  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
}

function writeCookie(name: string, value: string): void {
  if (typeof document === 'undefined') return;
  document.cookie = `${name}=${encodeURIComponent(value)}; path=/; max-age=31536000; SameSite=Lax`;
}

function persistSessionId(value: string): void {
  if (typeof window !== 'undefined' && window.localStorage) {
    localStorage.setItem(SESSION_ID_KEY, value);
  }
  writeCookie(SESSION_ID_COOKIE, value);
}

function extractApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const apiMessage = error.response?.data?.error;
    if (typeof apiMessage === 'string' && apiMessage.trim().length > 0) {
      return apiMessage;
    }
  }

  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return fallback;
}

function normalizeAnalysisResponse(data: Partial<AnalysisResponse> | null | undefined): AnalysisResponse {
  return {
    circuit_data: Array.isArray(data?.circuit_data) ? data.circuit_data : [],
    issues_on_map: Array.isArray(data?.issues_on_map) ? data.issues_on_map : [],
    driving_analysis: typeof data?.driving_analysis === 'string' ? data.driving_analysis : '',
    telemetry_analysis: typeof data?.telemetry_analysis === 'string' ? data.telemetry_analysis : '',
    setup_analysis: data?.setup_analysis ?? {},
    full_setup: data?.full_setup ?? {},
    session_stats: data?.session_stats ?? null,
    laps_data: Array.isArray(data?.laps_data) ? data.laps_data : [],
    agent_reports: Array.isArray(data?.agent_reports) ? data.agent_reports : [],
    telemetry_summary_sent: typeof data?.telemetry_summary_sent === 'string' ? data.telemetry_summary_sent : '',
    chief_reasoning: typeof data?.chief_reasoning === 'string' ? data.chief_reasoning : '',
    telemetry_series: Array.isArray(data?.telemetry_series) ? data.telemetry_series : [],
  };
}

function getSessionId(): string {
  if (!sessionId) {
    if (typeof window !== 'undefined' && window.localStorage) {
      const cookieValue = readCookie(SESSION_ID_COOKIE);
      const stored = localStorage.getItem(SESSION_ID_KEY);

      // Cookie is shared across localhost ports while localStorage is origin-scoped.
      // Prefer the cookie to avoid drifting into an empty session namespace after reloads/deploys.
      const existing = cookieValue || stored;

      if (existing) {
        sessionId = existing;
      } else {
        sessionId = `web-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
      }

      persistSessionId(sessionId);
    } else {
      sessionId = `web-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
    }
  }
  return sessionId;
}

const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  timeout: 300_000, // 5min for analysis
});

api.interceptors.request.use((config) => {
  config.headers['X-Client-Session-Id'] = getSessionId();
  return config;
});

api.interceptors.response.use((response) => {
  const headerValue = response.headers?.['X-Client-Session-Id'] ?? response.headers?.['x-client-session-id'];
  if (typeof headerValue === 'string' && headerValue.trim().length > 0) {
    sessionId = headerValue.trim();
    persistSessionId(sessionId);
  }
  return response;
});

// ── Health ──

export async function healthCheck(): Promise<{ status: string; ollama: boolean }> {
  const { data } = await api.get('/health');
  return data;
}

// ── Models ──

export interface ModelInfo {
  name: string;
  size: number;
  modified_at: string;
}

export async function listModels(): Promise<ModelInfo[]> {
  const { data } = await api.get('/models');
  return data.models ?? [];
}

// ── Sessions ──

export interface SessionInfo {
  id: string;
  telemetry: string;
  svm: string;
}

export async function listSessions(): Promise<SessionInfo[]> {
  const { data } = await api.get('/sessions');
  return data.sessions ?? [];
}

export async function deleteSession(sessionId: string): Promise<void> {
  await api.delete(`/sessions/${sessionId}`);
}

// ── Session state helpers (localStorage) ──

export type SessionState = 'uploaded' | 'telemetry_loaded' | 'analysis_complete';

const SESSION_STATES_KEY = 'rf2_session_states';

export interface SessionSnapshot {
  session_id: string;
  saved_at: string;
  state: SessionState;
  locked_parameters: string[];
  analysis_result: AnalysisResponse | null;
  full_setup: Record<string, SetupChange[]> | null;
}

function readSessionStates(): Record<string, SessionState> {
  if (typeof window === 'undefined' || !window.localStorage) return {};
  try {
    return JSON.parse(localStorage.getItem(SESSION_STATES_KEY) ?? '{}');
  } catch {
    return {};
  }
}

export function getSessionStates(): Record<string, SessionState> {
  return readSessionStates();
}

export function setSessionState(id: string, state: SessionState): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  const current = readSessionStates();
  current[id] = state;
  localStorage.setItem(SESSION_STATES_KEY, JSON.stringify(current));
}

export function removeSessionState(id: string): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  const current = readSessionStates();
  delete current[id];
  localStorage.setItem(SESSION_STATES_KEY, JSON.stringify(current));
}

export function clearAllSessionStates(): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  localStorage.removeItem(SESSION_STATES_KEY);
}

// Saved UI state per backend session (one entry per session_id, overwritten on save)
const SESSION_SNAPSHOTS_LIST_KEY = 'rf2_snapshots_v2';
const LAST_LOCKED_PARAMS_KEY = 'rf2_last_locked_parameters_v1';

// Keep snapshot payload bounded to avoid browser localStorage quota crashes.
const SNAPSHOT_MAX_AGENT_REPORT_CHARS = 1200;

function normalizeSnapshot(raw: Partial<SessionSnapshot>): SessionSnapshot {
  const savedAt = raw.saved_at ?? new Date().toISOString();
  const sessionId = raw.session_id ?? 'local';
  return {
    session_id: sessionId,
    saved_at: savedAt,
    state: raw.state ?? 'telemetry_loaded',
    locked_parameters: Array.isArray(raw.locked_parameters) ? raw.locked_parameters : [],
    analysis_result: raw.analysis_result ?? null,
    full_setup: raw.full_setup ?? null,
  };
}

function compactAnalysisForSnapshot(analysis: AnalysisResponse | null): AnalysisResponse | null {
  if (!analysis) return null;

  return {
    ...analysis,
    // These arrays dominate storage usage and are reloaded from backend on load.
    circuit_data: [],
    issues_on_map: [],
    laps_data: [],
    telemetry_series: [],
    agent_reports: Array.isArray(analysis.agent_reports)
      ? analysis.agent_reports.map((report) => ({
          section: report?.section ?? '',
          raw: typeof report?.raw === 'string'
            ? report.raw.slice(0, SNAPSHOT_MAX_AGENT_REPORT_CHARS)
            : '',
        }))
      : [],
  };
}

function compactSnapshotForStorage(snapshot: SessionSnapshot): SessionSnapshot {
  return {
    ...snapshot,
    analysis_result: compactAnalysisForSnapshot(snapshot.analysis_result),
  };
}

function persistSnapshotsWithFallback(snapshots: SessionSnapshot[]): void {
  const sorted = [...snapshots].sort((a, b) => b.saved_at.localeCompare(a.saved_at));

  const attempts: SessionSnapshot[][] = [
    sorted,
    sorted.map((entry) => compactSnapshotForStorage(entry)),
    sorted.length > 0 ? [compactSnapshotForStorage(sorted[0])] : [],
  ];

  for (const candidate of attempts) {
    try {
      localStorage.setItem(SESSION_SNAPSHOTS_LIST_KEY, JSON.stringify(candidate));
      return;
    } catch {
      // Continue trying with a smaller payload.
    }
  }

  throw new Error('No se pudo guardar por limite de almacenamiento del navegador. Usa "Limpiar todo" y vuelve a intentar.');
}

function readAllSnapshots(): SessionSnapshot[] {
  if (typeof window === 'undefined' || !window.localStorage) return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(SESSION_SNAPSHOTS_LIST_KEY) ?? '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed.map((entry) => normalizeSnapshot(entry as Partial<SessionSnapshot>));
  } catch {
    return [];
  }
}

/** Returns saved state for one backend session (or null if none). */
export function getSessionSnapshot(id: string): SessionSnapshot | null {
  const all = readAllSnapshots().filter((s) => s.session_id === id);
  if (all.length === 0) return null;
  all.sort((a, b) => b.saved_at.localeCompare(a.saved_at));
  return all[0];
}

/** Saves snapshot for a session, overwriting previous saved state for that session. */
export function saveSessionSnapshot(snapshot: SessionSnapshot): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  const normalized = compactSnapshotForStorage(normalizeSnapshot(snapshot));
  const all = readAllSnapshots().filter((s) => s.session_id !== normalized.session_id);
  all.push(normalized);
  persistSnapshotsWithFallback(all);
}

/** Removes saved state for one backend session. */
export function removeSessionSnapshot(sessionId: string): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  const all = readAllSnapshots().filter(
    (s) => s.session_id !== sessionId,
  );
  persistSnapshotsWithFallback(all);
}

export function clearAllSessionSnapshots(): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  localStorage.removeItem(SESSION_SNAPSHOTS_LIST_KEY);
}

/** Stores a global copy of the latest locked-parameter selection (overwritten on each save). */
export function saveLastLockedParameters(params: string[]): void {
  if (typeof window === 'undefined' || !window.localStorage) return;
  const normalized = Array.from(new Set(params.map((p) => p.trim()).filter((p) => p.length > 0)));
  localStorage.setItem(LAST_LOCKED_PARAMS_KEY, JSON.stringify(normalized));
}

/** Returns the latest locked-parameter selection copy, or [] if unavailable. */
export function getLastLockedParameters(): string[] {
  if (typeof window === 'undefined' || !window.localStorage) return [];
  try {
    const parsed = JSON.parse(localStorage.getItem(LAST_LOCKED_PARAMS_KEY) ?? '[]');
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((entry): entry is string => typeof entry === 'string')
      .map((entry) => entry.trim())
      .filter((entry) => entry.length > 0);
  } catch {
    return [];
  }
}

export async function getSetup(sessionId: string): Promise<Record<string, SetupChange[]>> {
  const { data } = await api.get(`/setup/${sessionId}`);
  return data.full_setup ?? {};
}

export async function cleanup(): Promise<void> {
  await api.post('/cleanup');
}

// ── Upload (chunked) ──

interface UploadInit {
  upload_id: string;
  chunk_size: number;
  filename: string;
}

interface UploadComplete {
  filename: string;
  session_id: string;
  bytes_received: number;
}

export async function uploadFile(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<string> {
  // Init
  const { data: init } = await api.post<UploadInit>('/uploads/init', {
    filename: file.name,
    total_size: file.size,
  });

  const chunkSize = init.chunk_size;
  const totalChunks = Math.ceil(file.size / chunkSize);

  // Chunks
  for (let i = 0; i < totalChunks; i++) {
    const start = i * chunkSize;
    const end = Math.min(start + chunkSize, file.size);
    const chunk = file.slice(start, end);

    await api.put(`/uploads/${init.upload_id}/chunk?chunk_index=${i}`, chunk, {
      headers: { 'Content-Type': 'application/octet-stream' },
    });

    onProgress?.(((i + 1) / totalChunks) * 100);
  }

  // Complete
  const { data: complete } = await api.post<UploadComplete>(`/uploads/${init.upload_id}/complete`);
  return complete.session_id;
}

// ── Analysis ──

export interface GPSPoint {
  lat: number;
  lon: number;
}

export interface IssueMarker {
  lat: number;
  lon: number;
  description: string;
  severity: string;
}

export interface SetupChange {
  parameter: string;
  old_value: string;
  new_value: string;
  reason: string;
  change_pct: string; // e.g. "+5.3%" — returned as string by backend
}

export interface LapStats {
  lap: number;
  duration: number;
  avg_speed: number;
  max_speed: number;
  avg_throttle?: number;
  max_throttle?: number;
  avg_brake?: number;
  max_brake?: number;
  avg_rpm?: number;
}

export interface TelemetrySample {
  t: number;
  spd: number;
  thr: number;
  brk: number;
  rpm: number;
  gear: number;
  lat: number;
  lon: number;
  lap: number;

  // Steering / drivetrain
  steer: number;
  steer_torque: number;
  clutch: number;

  // G-forces
  g_lat: number;
  g_long: number;
  g_vert: number;

  // Ride heights (mm)
  ride_h_fl: number;
  ride_h_fr: number;
  ride_h_rl: number;
  ride_h_rr: number;

  // Brake temperatures (°C)
  brake_t_fl: number;
  brake_t_fr: number;
  brake_t_rl: number;
  brake_t_rr: number;
  brake_bias: number;

  // Tyre pressures (kPa)
  tyre_p_fl: number;
  tyre_p_fr: number;
  tyre_p_rl: number;
  tyre_p_rr: number;

  // Tyre temp centre (°C)
  tyre_t_fl: number;
  tyre_t_fr: number;
  tyre_t_rl: number;
  tyre_t_rr: number;

  // Tyre temp inner/outer (°C)
  tyre_t_fl_inner: number;
  tyre_t_fl_outer: number;
  tyre_t_fr_inner: number;
  tyre_t_fr_outer: number;
  tyre_t_rl_inner: number;
  tyre_t_rl_outer: number;
  tyre_t_rr_inner: number;
  tyre_t_rr_outer: number;

  // Tyre wear (0-1)
  tyre_w_fl: number;
  tyre_w_fr: number;
  tyre_w_rl: number;
  tyre_w_rr: number;

  // Tyre load (N)
  tyre_l_fl: number;
  tyre_l_fr: number;
  tyre_l_rl: number;
  tyre_l_rr: number;

  // Grip fraction (0-1)
  grip_fl: number;
  grip_fr: number;
  grip_rl: number;
  grip_rr: number;

  // Wheel rotation speed (rad/s)
  wheel_sp_fl: number;
  wheel_sp_fr: number;
  wheel_sp_rl: number;
  wheel_sp_rr: number;

  // Engine
  oil_temp: number;
  water_temp: number;
  fuel_level: number;
}

export interface SessionStats {
  circuit_name?: string;
  total_laps: number;
  best_lap_time: number;
  avg_lap_time: number;
  laps: LapStats[];
}

export interface AnalysisResponse {
  circuit_data: GPSPoint[];
  issues_on_map: IssueMarker[];
  driving_analysis: string;
  telemetry_analysis: string;
  setup_analysis: Record<string, SetupChange[]>;
  full_setup: Record<string, SetupChange[]>;
  session_stats: SessionStats | null;
  laps_data: LapStats[];
  agent_reports: { section: string; raw: string }[];
  telemetry_summary_sent: string;
  chief_reasoning: string;
  telemetry_series: TelemetrySample[];
}

export async function analyzeFiles(
  telemetryFile: File,
  svmFile: File,
  model?: string,
  provider?: string,
  fixedParams?: string[],
): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('telemetry', telemetryFile);
  form.append('svm', svmFile);
  if (model) form.append('model', model);
  if (provider) form.append('provider', provider);
  for (const param of fixedParams ?? []) {
    form.append('fixed_params', param);
  }

  const { data } = await api.post<AnalysisResponse>('/analyze', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function analyzeSession(
  sessionId: string,
  model?: string,
  provider?: string,
  fixedParams?: string[],
): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('session_id', sessionId);
  if (model) form.append('model', model);
  if (provider) form.append('provider', provider);
  for (const param of fixedParams ?? []) {
    form.append('fixed_params', param);
  }

  const { data } = await api.post<AnalysisResponse>('/analyze_session', form);
  return data;
}

export async function loadSessionTelemetry(sessionId: string): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('session_id', sessionId);

  try {
    const { data } = await api.post<AnalysisResponse>('/session_telemetry', form);
    const normalized = normalizeAnalysisResponse(data);

    if (normalized.telemetry_series.length === 0 && normalized.circuit_data.length === 0) {
      throw new Error('La sesión no devolvió muestras de telemetría ni datos GPS');
    }

    return normalized;
  } catch (error: unknown) {
    throw new Error(extractApiErrorMessage(error, 'No se pudo cargar la telemetría de la sesión'));
  }
}

export interface ProgressEvent {
  type: 'progress' | 'error';
  agent: string;
  section?: string;
  message: string;
}

/**
 * Starts analysis with SSE streaming. Calls onProgress for each agent event,
 * then resolves with the final AnalysisResponse when the result event arrives.
 */
export async function analyzeSessionStream(
  sessionId: string,
  model: string | undefined,
  provider: string | undefined,
  fixedParams: string[] | undefined,
  onProgress: (ev: ProgressEvent) => void,
): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('session_id', sessionId);
  if (model) form.append('model', model);
  if (provider) form.append('provider', provider);
  for (const param of fixedParams ?? []) {
    form.append('fixed_params', param);
  }

  const headers: Record<string, string> = {
    'X-Client-Session-Id': getSessionId(),
  };

  const response = await fetch(`${API_URL}/analyze_stream`, {
    method: 'POST',
    headers,
    body: form,
  });

  if (!response.ok || !response.body) {
    const text = await response.text().catch(() => '');
    throw new Error(`HTTP ${response.status}: ${text}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE messages are separated by double newlines
    const parts = buffer.split('\n\n');
    buffer = parts.pop() ?? '';

    for (const part of parts) {
      const eventMatch = part.match(/^event:\s*(\S+)/m);
      const dataMatch = part.match(/^data:\s*(.+)/ms);
      if (!dataMatch) continue;

      const eventType = eventMatch?.[1] ?? 'message';
      const payload = JSON.parse(dataMatch[1].trim());

      if (eventType === 'progress' || eventType === 'error') {
        onProgress(payload as ProgressEvent);
      } else if (eventType === 'result') {
        return payload as AnalysisResponse;
      }
      // 'done' event — loop will exit naturally
    }
  }

  throw new Error('Stream ended without a result event');
}

// ── Tracks ──

export interface TrackInfo {
  id: string;
  name: string;
  country: string;
  length_km: number;
  turns: number;
}

export async function listTracks(): Promise<TrackInfo[]> {
  const { data } = await api.get('/tracks');
  return data.tracks ?? [];
}
