/**
 * Targeted text node test: renders TelemetryScreen WITH full telemetry data.
 * The error "Unexpected text node" only appears in the FULL render (with data).
 */
import React from 'react';
import { create, act } from 'react-test-renderer';
import type { AnalysisResponse } from '../../src/api';

// Build a minimal but complete AnalysisResponse with actual numbers
const FAKE_SAMPLE = {
  t: 0.01, lap: 1,
  spd: 120, thr: 0.75, brk: 0, rpm: 8500, gear: 4,
  tyre_t_fl: 95, tyre_t_fr: 96, tyre_t_rl: 94, tyre_t_rr: 97,
  tyre_p_fl: 170, tyre_p_fr: 170, tyre_p_rl: 168, tyre_p_rr: 169,
  tyre_w_fl: 0.9, tyre_w_fr: 0.9, tyre_w_rl: 0.88, tyre_w_rr: 0.87,
  tyre_l_fl: 3200, tyre_l_fr: 3200, tyre_l_rl: 3100, tyre_l_rr: 3150,
  grip_fl: 0.95, grip_fr: 0.95, grip_rl: 0.92, grip_rr: 0.93,
  wheel_sp_fl: 85, wheel_sp_fr: 85, wheel_sp_rl: 84, wheel_sp_rr: 84,
  ride_h_fl: 32, ride_h_fr: 31, ride_h_rl: 35, ride_h_rr: 36,
  g_lat: 0.3, g_long: -0.1, g_vert: 1.0,
  brake_t_fl: 320, brake_t_fr: 315, brake_t_rl: 280, brake_t_rr: 275,
  brake_bias: 56,
  oil_temp: 105, water_temp: 95, fuel_level: 45, clutch: 0,
  steer: 5, steer_torque: 2,
  lat: 25.487, lon: 51.447,
};

// Add enough samples to show charts (need > 2 samples)
function makeSamples(count: number) {
  return Array.from({ length: count }, (_, i) => ({
    ...FAKE_SAMPLE,
    t: i * 0.01,
    lap: i < count / 2 ? 1 : 2,
    spd: 100 + (i % 60),
  }));
}

const FAKE_ANALYSIS = {
  telemetry_series: makeSamples(200),
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
  laps_data: null,
  circuit_data: [{ lat: 25.487, lon: 51.447 }, { lat: 25.488, lon: 51.448 }, { lat: 25.489, lon: 51.449 }],
  driving_analysis: 'Análisis de conducción **negrita** y *cursiva*.',
  setup_analysis: {},
  chief_reasoning: '',
  issues_on_map: [],
  full_setup: {},
};

// ---- Mocks ----
jest.mock('../../src/api', () => ({
  healthCheck: jest.fn().mockResolvedValue({ status: 'ok' }),
  listModels: jest.fn().mockResolvedValue([]),
  listSessions: jest.fn().mockResolvedValue([]),
  listTracks: jest.fn().mockResolvedValue([]),
  getSessionStates: jest.fn().mockReturnValue({}),
  setSessionState: jest.fn(),
  loadSessionTelemetry: jest.fn().mockResolvedValue(null),
}));

let mockAnalysisResult = FAKE_ANALYSIS;

jest.mock('../../src/store/useAppStore', () => ({
  useAppStore: jest.fn((selector) => {
    const state = {
      serverStatus: 'ok',
      setServerStatus: jest.fn(),
      telemetryFile: null, svmFile: null,
      setTelemetryFile: jest.fn(), setSvmFile: jest.fn(),
      uploadProgress: 0, setUploadProgress: jest.fn(),
      isUploading: false, setUploading: jest.fn(),
      activeSessionId: 'session-123',
      setActiveSessionId: jest.fn(),
      // Return full analysis data to exercise full render path
      analysisResult: mockAnalysisResult,
      setAnalysisResult: jest.fn(),
      analysisError: null, setAnalysisError: jest.fn(),
      isAnalyzing: false, setAnalyzing: jest.fn(),
      models: [], setModels: jest.fn(),
      selectedModel: 'llama3.2:latest', setSelectedModel: jest.fn(),
      selectedProvider: 'ollama',
      sessions: [], setSessions: jest.fn(),
      tracks: [], setTracks: jest.fn(),
      fullSetup: null, setFullSetup: jest.fn(),
      lockedParameters: new Set(),
      toggleLockedParameter: jest.fn(),
    };
    return typeof selector === 'function' ? selector(state) : state;
  }),
}));

jest.mock('../../src/components/TelemetryCharts', () => {
  const React = require('react');
  const { View, Text } = require('react-native');
  return {
    __esModule: true,
    default: ({ samples }: { samples: unknown[] }) =>
      React.createElement(View, null,
        React.createElement(Text, null, `Charts: ${samples?.length ?? 0} samples`)
      ),
  };
});

jest.mock('../../src/components/CircuitMap', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    __esModule: true,
    default: () => React.createElement(View, null),
  };
});

import TelemetryScreen from '../../app/(tabs)/telemetry';

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
    // ignore render errors; only check text node errors
  } finally {
    console.error = origError;
  }

  if (capturedErrors.length > 0) {
    throw new Error(
      `[${name}] Detected text-node-in-View errors:\n` + capturedErrors.join('\n')
    );
  }
}

describe('TelemetryScreen full render — text node detection', () => {
  test('TelemetryScreen WITH full data has no text nodes in View', () => {
    renderAndCheckTextNodes('TelemetryScreen(full)', TelemetryScreen);
  });

  test('TelemetryScreen WITH full data including wide table (isWide=true)', () => {
    // Mock wide screen dimension
    jest.spyOn(require('react-native'), 'useWindowDimensions')
      .mockReturnValue({ width: 1200, height: 900, scale: 1, fontScale: 1 });

    renderAndCheckTextNodes('TelemetryScreen(wide)', TelemetryScreen);
  });
});
