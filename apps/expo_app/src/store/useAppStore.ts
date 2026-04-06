import { create } from 'zustand';
import type { AnalysisResponse, SessionInfo, ModelInfo, TrackInfo } from '../api';

interface AppState {
  // Health
  serverStatus: 'unknown' | 'ok' | 'degraded' | 'offline';
  setServerStatus: (s: AppState['serverStatus']) => void;

  // Sessions
  sessions: SessionInfo[];
  setSessions: (s: SessionInfo[]) => void;

  // Upload
  uploadProgress: number;
  isUploading: boolean;
  setUploadProgress: (p: number) => void;
  setUploading: (v: boolean) => void;

  // Analysis
  isAnalyzing: boolean;
  analysisResult: AnalysisResponse | null;
  analysisError: string | null;
  setAnalyzing: (v: boolean) => void;
  setAnalysisResult: (r: AnalysisResponse | null) => void;
  setAnalysisError: (e: string | null) => void;

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
}

export const useAppStore = create<AppState>((set) => ({
  serverStatus: 'unknown',
  setServerStatus: (serverStatus) => set({ serverStatus }),

  sessions: [],
  setSessions: (sessions) => set({ sessions }),

  uploadProgress: 0,
  isUploading: false,
  setUploadProgress: (uploadProgress) => set({ uploadProgress }),
  setUploading: (isUploading) => set({ isUploading }),

  isAnalyzing: false,
  analysisResult: null,
  analysisError: null,
  setAnalyzing: (isAnalyzing) => set({ isAnalyzing }),
  setAnalysisResult: (analysisResult) => set({ analysisResult, analysisError: null }),
  setAnalysisError: (analysisError) => set({ analysisError, analysisResult: null }),

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
}));
