import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { AnalysisResponse, SessionInfo, ModelInfo, TrackInfo, SetupChange } from '../api';

interface AppState {
  // Health
  serverStatus: 'unknown' | 'ok' | 'degraded' | 'offline';
  setServerStatus: (s: AppState['serverStatus']) => void;

  // Sessions
  sessions: SessionInfo[];
  activeSessionId: string | null;
  setSessions: (s: SessionInfo[]) => void;
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
  setModels: (m: ModelInfo[]) => void;
  setSelectedModel: (m: string) => void;
  setSelectedProvider: (p: string) => void;

  // Tracks
  tracks: TrackInfo[];
  setTracks: (t: TrackInfo[]) => void;

  // Selected files
  telemetryFile: File | null;
  svmFile: File | null;
  setTelemetryFile: (f: File | null) => void;
  setSvmFile: (f: File | null) => void;

  // Locked parameters (prevent AI from suggesting changes)
  lockedParameters: Set<string>;
  toggleLockedParameter: (param: string) => void;
  setLockedParameters: (params: Set<string>) => void;
  clearLockedParameters: () => void;
}

export const useAppStore = create<AppState>()(persist((set) => ({
  serverStatus: 'unknown',
  setServerStatus: (serverStatus) => set({ serverStatus }),

  sessions: [],
  activeSessionId: null,
  setSessions: (sessions) => set({ sessions }),
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
  selectedProvider: 'ollama',
  setModels: (models) => set({ models }),
  setSelectedModel: (selectedModel) => set({ selectedModel }),
  setSelectedProvider: (selectedProvider) => set({ selectedProvider }),

  tracks: [],
  setTracks: (tracks) => set({ tracks }),

  telemetryFile: null,
  svmFile: null,
  setTelemetryFile: (telemetryFile) => set({ telemetryFile }),
  setSvmFile: (svmFile) => set({ svmFile }),

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
  partialize: (state) => ({
    activeSessionId: state.activeSessionId,
    selectedModel: state.selectedModel,
    selectedProvider: state.selectedProvider,
  }),
}));
