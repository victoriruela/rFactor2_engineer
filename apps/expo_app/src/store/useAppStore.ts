import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AnalysisResponse, ModelInfo, TrackInfo, SetupChange, PreparsedAnalyzePayload } from '../api';

const DEFAULT_OLLAMA_BASE_URL = process.env.EXPO_PUBLIC_OLLAMA_BASE_URL ?? 'https://www.ollama.com';

function isInvalidOllamaUrl(url: string | null | undefined): boolean {
  if (!url) return true;
  const normalized = url.trim().toLowerCase();
  return normalized.length === 0 || normalized === 'undefined' || normalized === 'null';
}

interface AppState {
  // Auth
  jwt: string | null;
  authUsername: string | null;
  isAdmin: boolean;
  setAuth: (jwt: string, username: string, isAdmin: boolean) => void;
  clearAuth: () => void;

  // Health
  serverStatus: 'unknown' | 'ok' | 'degraded' | 'offline';
  setServerStatus: (s: AppState['serverStatus']) => void;

  // Active session
  activeSessionId: string | null;
  setActiveSessionId: (id: string | null) => void;

  // Upload
  uploadProgress: number;
  isUploading: boolean;
  setUploadProgress: (p: number) => void;
  setUploading: (v: boolean) => void;

  // Analysis
  isAnalyzing: boolean;
  analysisResult: AnalysisResponse | null;
  analysisError: string | null;
  fullSetup: Record<string, SetupChange[]> | null;
  setAnalyzing: (v: boolean) => void;
  setAnalysisResult: (r: AnalysisResponse | null) => void;
  setAnalysisError: (e: string | null) => void;
  setFullSetup: (data: Record<string, SetupChange[]> | null) => void;

  // Models
  models: ModelInfo[];
  selectedModel: string;
  selectedProvider: string;
  ollamaBaseUrl: string;
  ollamaApiKey: string;
  setModels: (m: ModelInfo[]) => void;
  setSelectedModel: (m: string) => void;
  setSelectedProvider: (p: string) => void;
  setOllamaBaseUrl: (url: string) => void;
  setOllamaApiKey: (key: string) => void;

  // Tracks
  tracks: TrackInfo[];
  setTracks: (t: TrackInfo[]) => void;

  // Selected files
  telemetryFile: File | null;
  svmFile: File | null;
  setTelemetryFile: (f: File | null) => void;
  setSvmFile: (f: File | null) => void;

  // Client-preparsed payload (.ld + .svm)
  preparsedPayload: PreparsedAnalyzePayload | null;
  setPreparsedPayload: (payload: PreparsedAnalyzePayload | null) => void;

  // Locked parameters (prevent AI from suggesting changes)
  lockedParameters: Set<string>;
  toggleLockedParameter: (param: string) => void;
  setLockedParameters: (params: Set<string>) => void;
  clearLockedParameters: () => void;
}

export const useAppStore = create<AppState>()(persist((set) => ({
  jwt: null,
  authUsername: null,
  isAdmin: false,
  setAuth: (jwt, authUsername, isAdmin) => set({ jwt, authUsername, isAdmin }),
  clearAuth: () => set({ jwt: null, authUsername: null, isAdmin: false, ollamaApiKey: '', selectedModel: 'llama3.2:latest' }),

  serverStatus: 'unknown',
  setServerStatus: (serverStatus) => set({ serverStatus }),

  activeSessionId: null,
  setActiveSessionId: (activeSessionId) => set({ activeSessionId }),

  uploadProgress: 0,
  isUploading: false,
  setUploadProgress: (uploadProgress) => set({ uploadProgress }),
  setUploading: (isUploading) => set({ isUploading }),

  isAnalyzing: false,
  analysisResult: null,
  analysisError: null,
  fullSetup: null,
  setAnalyzing: (isAnalyzing) => set({ isAnalyzing }),
  setAnalysisResult: (analysisResult) => set({ analysisResult, analysisError: null }),
  setAnalysisError: (analysisError) => set({ analysisError }),
  setFullSetup: (fullSetup) => set({ fullSetup }),

  models: [],
  selectedModel: 'llama3.2:latest',
  selectedProvider: 'ollama_cloud',
  ollamaBaseUrl: DEFAULT_OLLAMA_BASE_URL,
  ollamaApiKey: '',
  setModels: (models) => set({ models }),
  setSelectedModel: (selectedModel) => set({ selectedModel }),
  setSelectedProvider: (selectedProvider) => set({ selectedProvider }),
  setOllamaBaseUrl: (ollamaBaseUrl) => set({ ollamaBaseUrl }),
  setOllamaApiKey: (ollamaApiKey) => set({ ollamaApiKey }),

  tracks: [],
  setTracks: (tracks) => set({ tracks }),

  telemetryFile: null,
  svmFile: null,
  setTelemetryFile: (telemetryFile) => set({ telemetryFile }),
  setSvmFile: (svmFile) => set({ svmFile }),

  preparsedPayload: null,
  setPreparsedPayload: (preparsedPayload) => set({ preparsedPayload }),

  lockedParameters: new Set(),
  toggleLockedParameter: (param) => set((state) => {
    const newLocked = new Set(state.lockedParameters);
    if (newLocked.has(param)) {
      newLocked.delete(param);
    } else {
      newLocked.add(param);
    }
    return { lockedParameters: newLocked };
  }),
  setLockedParameters: (lockedParameters) => set({ lockedParameters }),
  clearLockedParameters: () => set({ lockedParameters: new Set() }),
}), {
  name: 'rf2-app-store',
  version: 5,
  migrate: () => ({}), // clear stale persisted data on version bump
  onRehydrateStorage: () => (state) => {
    if (!state) return;
    // Reset transient UI state on page load.
    // jwt, authUsername, isAdmin, ollamaApiKey, selectedModel persist across reloads.
    state.setActiveSessionId(null);
    state.setOllamaBaseUrl(DEFAULT_OLLAMA_BASE_URL);
    state.setSelectedProvider('ollama_cloud');
  },
  // jwt, auth, ollamaApiKey, selectedModel survive reloads; clearAuth clears everything
  partialize: (state) => ({ jwt: state.jwt, authUsername: state.authUsername, isAdmin: state.isAdmin, ollamaApiKey: state.ollamaApiKey, selectedModel: state.selectedModel }),
}));
