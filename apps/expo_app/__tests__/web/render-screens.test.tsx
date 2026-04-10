/**
 * Web rendering tests — catch "Unexpected text node in View" errors.
 * Intercepts console.error to detect RN Web's text-node validation warning.
 */
import React from 'react';

// ---- Mocks ----
jest.mock('../../src/api', () => ({
  healthCheck: jest.fn().mockResolvedValue({ status: 'ok' }),
  listModels: jest.fn().mockResolvedValue([]),
  listSessions: jest.fn().mockResolvedValue([]),
  listTracks: jest.fn().mockResolvedValue([]),
  analyzeFiles: jest.fn().mockResolvedValue({}),
  analyzeSessionStream: jest.fn().mockResolvedValue({}),
  uploadFile: jest.fn().mockResolvedValue('session-123'),
  getSetup: jest.fn().mockResolvedValue({}),
  loadSessionTelemetry: jest.fn().mockResolvedValue({ telemetry_series: [], session_stats: null, laps_data: null }),
  cleanup: jest.fn().mockResolvedValue({}),
  deleteSession: jest.fn().mockResolvedValue({}),
  setSessionState: jest.fn(),
  getSessionStates: jest.fn().mockReturnValue({}),
  removeSessionState: jest.fn(),
  clearAllSessionStates: jest.fn(),
}));

jest.mock('../../src/store/useAppStore', () => ({
  useAppStore: jest.fn((selector) => {
    const state = {
      serverStatus: 'ok',
      setServerStatus: jest.fn(),
      telemetryFile: null,
      svmFile: null,
      setTelemetryFile: jest.fn(),
      setSvmFile: jest.fn(),
      uploadProgress: 0,
      setUploadProgress: jest.fn(),
      isUploading: false,
      setUploading: jest.fn(),
      activeSessionId: null,
      setActiveSessionId: jest.fn(),
      analysisResult: null,
      setAnalysisResult: jest.fn(),
      analysisError: null,
      setAnalysisError: jest.fn(),
      isAnalyzing: false,
      setAnalyzing: jest.fn(),
      models: [],
      setModels: jest.fn(),
      selectedModel: 'llama3.2:latest',
      setSelectedModel: jest.fn(),
      selectedProvider: 'ollama',
      sessions: [],
      setSessions: jest.fn(),
      tracks: [],
      setTracks: jest.fn(),
      fullSetup: null,
      setFullSetup: jest.fn(),
      lockedParameters: new Set(),
      toggleLockedParameter: jest.fn(),
    };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

jest.mock('expo-document-picker', () => ({
  getDocumentAsync: jest.fn().mockResolvedValue({ type: 'cancel' }),
}));

// ---- Import screens ----
// We test each component by rendering them with react-test-renderer
// and checking console.error for text node warnings.
import { create, act } from 'react-test-renderer';

function renderAndCheckTextNodes(name: string, Component: React.ComponentType) {
  const capturedErrors: string[] = [];
  const origError = console.error;
  console.error = (...args: unknown[]) => {
    const msg = (args[0] ?? '') as string;
    if (typeof msg === 'string' && msg.includes('Unexpected text node')) {
      capturedErrors.push(msg);
    }
    // Don't call origError to keep output clean
  };

  try {
    act(() => {
      create(React.createElement(Component));
    });
  } catch (_e) {
    // Swallow render errors (we only care about text node errors)
  } finally {
    console.error = origError;
  }

  if (capturedErrors.length > 0) {
    throw new Error(
      `[${name}] Detected ${capturedErrors.length} "Unexpected text node" error(s):\n` +
      capturedErrors.join('\n')
    );
  }
}

function renderModuleAndCheckTextNodes(name: string, modulePath: string) {
  jest.resetModules();
  jest.isolateModules(() => {
    const Component = require(modulePath).default as React.ComponentType;
    renderAndCheckTextNodes(name, Component);
  });
}

describe('Text node in View detection', () => {
  test('HomeScreen has no text nodes in View', () => {
    renderModuleAndCheckTextNodes('HomeScreen', '../../app/(tabs)/index');
  });

  test('UploadScreen has no text nodes in View', () => {
    renderModuleAndCheckTextNodes('UploadScreen', '../../app/(tabs)/upload');
  });

  test('AnalysisScreen has no text nodes in View', () => {
    renderModuleAndCheckTextNodes('AnalysisScreen', '../../app/(tabs)/analysis');
  });

  test('TelemetryScreen (no data) has no text nodes in View', () => {
    renderModuleAndCheckTextNodes('TelemetryScreen', '../../app/(tabs)/telemetry');
  });

  test('SessionsScreen has no text nodes in View', () => {
    renderModuleAndCheckTextNodes('SessionsScreen', '../../app/(tabs)/sessions');
  });

  test('TracksScreen has no text nodes in View', () => {
    renderModuleAndCheckTextNodes('TracksScreen', '../../app/(tabs)/tracks');
  });
});

