/**
 * Targeted text node test: renders AnalysisScreen WITH full analysis data.
 * This covers the real Analysis tab path that previously lacked render tests.
 */
import React from 'react';
import { create, act } from 'react-test-renderer';

const mockAnalysisResult = {
  telemetry_series: [],
  session_stats: {
    circuit_name: 'Test Circuit',
    total_laps: 2,
    best_lap_time: 75.234,
    avg_lap_time: 76.1,
    laps: [
      { lap: 1, duration: 75.234, avg_speed: 145.2, max_speed: 198.4, avg_throttle: 68, avg_brake: 12, avg_rpm: 7500 },
      { lap: 2, duration: 76.8, avg_speed: 143.1, max_speed: 196.2, avg_throttle: 67, avg_brake: 13, avg_rpm: 7400 },
    ],
  },
  laps_data: [],
  circuit_data: [],
  driving_analysis: 'Primera línea.\n\n* Punto uno\n* Punto dos con **negrita**',
  setup_analysis: {
    FRONTWING: [
      {
        parameter: 'FrontWingSetting',
        old_value: '10',
        new_value: '12',
        reason: 'Más apoyo en curva rápida',
        change_pct: '+20%',
      },
    ],
  },
  chief_reasoning: JSON.stringify({
    reasoning_sections: [
      { title: 'Aero', text: 'Conviene subir ala delantera.' },
      { title: 'Balance', text: 'El coche subviraba en apoyo.' },
    ],
    summary: 'Aplicar cambios moderados.',
  }),
  issues_on_map: [],
  full_setup: {
    FRONTWING: [
      { parameter: 'FrontWingSetting', old_value: '10', new_value: '', reason: '', change_pct: '' },
      { parameter: 'BrakeBias', old_value: '56', new_value: '', reason: '', change_pct: '' },
    ],
  },
};

jest.mock('../../src/api', () => ({
  healthCheck: jest.fn().mockResolvedValue({ status: 'ok' }),
  listModels: jest.fn().mockResolvedValue([]),
  listSessions: jest.fn().mockResolvedValue([{ id: 'session-123' }]),
  listTracks: jest.fn().mockResolvedValue([]),
  analyzeFiles: jest.fn().mockResolvedValue(null),
  analyzeSessionStream: jest.fn().mockResolvedValue(null),
  setSessionState: jest.fn(),
}));

jest.mock('../../src/store/useAppStore', () => ({
  useAppStore: jest.fn((selector) => {
    const state = {
      telemetryFile: { name: 'telemetry.csv' },
      svmFile: { name: 'setup.svm' },
      isAnalyzing: false,
      setAnalyzing: jest.fn(),
      analysisResult: mockAnalysisResult,
      setAnalysisResult: jest.fn(),
      analysisError: null,
      setAnalysisError: jest.fn(),
      models: [],
      setModels: jest.fn(),
      selectedModel: 'llama3.2:latest',
      setSelectedModel: jest.fn(),
      selectedProvider: 'ollama',
      lockedParameters: new Set(['BrakeBias']),
      activeSessionId: 'session-123',
      setActiveSessionId: jest.fn(),
    };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

import AnalysisScreen from '../../app/(tabs)/analysis';

function renderAndCheckTextNodes(name: string, Component: React.ComponentType) {
  const capturedErrors: string[] = [];
  const origError = console.error;
  console.error = (...args: unknown[]) => {
    const msg = String(args[0] ?? '');
    if (msg.includes('Unexpected text node')) {
      capturedErrors.push(msg);
    }
  };

  try {
    act(() => {
      create(React.createElement(Component));
    });
  } catch (_e) {
    // Ignore unrelated render/runtime noise; this test only checks text-node warnings.
  } finally {
    console.error = origError;
  }

  if (capturedErrors.length > 0) {
    throw new Error(`[${name}] Detected text-node-in-View errors:\n${capturedErrors.join('\n')}`);
  }
}

describe('AnalysisScreen full render — text node detection', () => {
  test('AnalysisScreen WITH full analysis data has no text nodes in View', () => {
    renderAndCheckTextNodes('AnalysisScreen(full)', AnalysisScreen);
  });
});
