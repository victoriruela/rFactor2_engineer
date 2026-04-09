import axios, { AxiosInstance } from 'axios';
import { resolveApiBaseUrl } from './baseUrl';

const API_URL = resolveApiBaseUrl({
  envApiUrl: process.env.EXPO_PUBLIC_API_URL,
  isWeb: typeof window !== 'undefined',
  windowOrigin: typeof window !== 'undefined' ? window.location.origin : undefined,
});

let sessionId: string | null = null;

const SESSION_ID_KEY = 'rf2_client_session_id';

function getSessionId(): string {
  if (!sessionId) {
    if (typeof window !== 'undefined' && window.localStorage) {
      const stored = localStorage.getItem(SESSION_ID_KEY);
      if (stored) {
        sessionId = stored;
      } else {
        sessionId = `web-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
        localStorage.setItem(SESSION_ID_KEY, sessionId);
      }
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
  avg_brake?: number;
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
): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('telemetry', telemetryFile);
  form.append('svm', svmFile);
  if (model) form.append('model', model);
  if (provider) form.append('provider', provider);

  const { data } = await api.post<AnalysisResponse>('/analyze', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function analyzeSession(
  sessionId: string,
  model?: string,
  provider?: string,
): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('session_id', sessionId);
  if (model) form.append('model', model);
  if (provider) form.append('provider', provider);

  const { data } = await api.post<AnalysisResponse>('/analyze_session', form);
  return data;
}

export async function loadSessionTelemetry(sessionId: string): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('session_id', sessionId);

  const { data } = await api.post<AnalysisResponse>('/session_telemetry', form);
  return data;
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
  onProgress: (ev: ProgressEvent) => void,
): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('session_id', sessionId);
  if (model) form.append('model', model);
  if (provider) form.append('provider', provider);

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
