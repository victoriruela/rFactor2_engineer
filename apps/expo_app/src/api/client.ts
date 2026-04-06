import axios, { AxiosInstance } from 'axios';

const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8080/api';

let sessionId: string | null = null;

function getSessionId(): string {
  if (!sessionId) {
    sessionId = `web-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
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

export async function cleanup(): Promise<void> {
  await api.post('/cleanup');
}

// ── Upload (chunked) ──

interface UploadInit {
  upload_id: string;
  chunk_size: number;
  filename: string;
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
  await api.post(`/uploads/${init.upload_id}/complete`);
  return init.upload_id;
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
  change_pct: number;
}

export interface LapStats {
  lap: number;
  duration: number;
  avg_speed: number;
  max_speed: number;
}

export interface AnalysisResponse {
  circuit_data: GPSPoint[];
  issues_on_map: IssueMarker[];
  driving_analysis: string;
  setup_analysis: Record<string, SetupChange[]>;
  full_setup: Record<string, SetupChange[]>;
  session_stats: {
    total_laps: number;
    best_lap_time: number;
    avg_lap_time: number;
    laps: LapStats[];
  };
  laps_data: LapStats[];
  agent_reports: { section: string; raw: string }[];
  telemetry_summary_sent: string;
  chief_reasoning: string;
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

export async function analyzeSession(sessionId: string): Promise<AnalysisResponse> {
  const form = new FormData();
  form.append('session_id', sessionId);

  const { data } = await api.post<AnalysisResponse>('/analyze_session', form);
  return data;
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
