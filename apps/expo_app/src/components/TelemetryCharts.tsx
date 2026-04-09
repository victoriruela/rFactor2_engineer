/**
 * TelemetryCharts — interactive telemetry viewer.
 * Shows Speed / Throttle+Brake / RPM / Gear as large full-width SVG line charts.
 * A draggable vertical cursor moves across all four charts simultaneously.
 */
import React, { useCallback, useMemo, useState } from 'react';
import { View, Text, StyleSheet, Dimensions, Platform } from 'react-native';
import Svg, { Line, Polyline, Rect, Text as SvgText, Circle } from 'react-native-svg';
import type { TelemetrySample } from '../api';

interface Props {
  samples: TelemetrySample[] | null | undefined;
  onIndexChange?: (index: number, sample: TelemetrySample) => void;
  showCursorBar?: boolean;
}

const CHART_HEIGHT = 160;
const PAD_LEFT = 46;
const PAD_RIGHT = 16;
const PAD_TOP = 10;
const PAD_BOTTOM = 26;
const GRID_LINES = 4; // number of horizontal grid divisions

interface ChartConfig {
  label: string;
  keys: Array<keyof TelemetrySample>;
  colors: string[];
  unit: string;
  formatFn?: (v: number) => string;
  smoothRadius?: number;
}

const CHARTS: ChartConfig[] = [
  {
    label: 'Velocidad',
    keys: ['spd'],
    colors: ['#4fc3f7'],
    unit: 'km/h',
    formatFn: (v) => `${v.toFixed(0)} km/h`,
    smoothRadius: 2,
  },
  {
    label: 'Acelerador / Freno',
    keys: ['thr', 'brk'],
    colors: ['#66bb6a', '#ef5350'],
    unit: '%',
    formatFn: (v) => `${(v * 100).toFixed(0)}%`,
    smoothRadius: 1,
  },
  {
    label: 'RPM',
    keys: ['rpm'],
    colors: ['#ffa726'],
    unit: 'rpm',
    formatFn: (v) => `${v.toFixed(0)}`,
    smoothRadius: 2,
  },
  {
    label: 'Marcha',
    keys: ['gear'],
    colors: ['#ce93d8'],
    unit: '',
    formatFn: (v) => `${Math.round(v)}ª`,
    smoothRadius: 0,
  },
];

function formatCursorTimestamp(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return '--:--.---';
  const totalMs = Math.round(seconds * 1000);
  const minutes = Math.floor(totalMs / 60000);
  const secondsPart = (totalMs % 60000) / 1000;
  return `${minutes.toString().padStart(2, '0')}:${secondsPart.toFixed(3).padStart(6, '0')}`;
}

function normalizePedalPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.abs(value) <= 1 ? value * 100 : value;
}

function finiteOrZero(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function formatPedalPercent(value: number): string {
  const pct = normalizePedalPercent(value);
  return `${pct.toLocaleString('es-ES', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;
}

function normalise(values: number[]): { norm: number[]; min: number; max: number } {
  if (values.length === 0) {
    return { norm: [], min: 0, max: 0 };
  }
  let mn = values[0];
  let mx = values[0];
  for (let i = 1; i < values.length; i++) {
    const value = values[i];
    if (value < mn) mn = value;
    if (value > mx) mx = value;
  }
  const range = mx - mn || 1;
  return {
    norm: values.map((v) => (v - mn) / range),
    min: mn,
    max: mx,
  };
}

function normaliseToRange(values: number[], min: number, max: number): number[] {
  const range = max - min || 1;
  return values.map((v) => {
    const n = (v - min) / range;
    return Math.max(0, Math.min(1, n));
  });
}

function smoothSeries(values: number[], windowRadius: number): number[] {
  if (values.length < 5 || windowRadius <= 0) return values;
  const out = new Array<number>(values.length);
  for (let i = 0; i < values.length; i++) {
    let sum = 0;
    let count = 0;
    const start = Math.max(0, i - windowRadius);
    const end = Math.min(values.length - 1, i + windowRadius);
    for (let j = start; j <= end; j++) {
      sum += values[j];
      count++;
    }
    out[i] = count > 0 ? sum / count : values[i];
  }
  return out;
}

/**
 * Remove pedal artifact zones that are physically impossible.
 * Any continuous active segment shorter than MIN_PEDAL_SAMPLES is zeroed out.
 * At 100 Hz, 30 samples = 300 ms — the minimum realistic pedal application.
 */
const BRAKE_ACTIVE_THRESHOLD = 5;    // % above which brake is considered "on"
const THROTTLE_ACTIVE_THRESHOLD = 5; // % above which throttle is considered "on"
const MIN_PEDAL_SAMPLES = 60;         // shorter zones are sensor artifacts (~600 ms at 100 Hz)

function removePedalArtifacts(values: number[], activeThreshold: number): number[] {
  if (values.length < MIN_PEDAL_SAMPLES) return values;
  const out = [...values];
  let i = 0;
  while (i < out.length) {
    if (out[i] <= activeThreshold) {
      i++;
      continue;
    }
    // Walk to end of active zone.
    const start = i;
    while (i < out.length && out[i] > activeThreshold) {
      i++;
    }
    const end = i - 1;
    // Short zone → artifact: zero it out.
    if (end - start + 1 < MIN_PEDAL_SAMPLES) {
      for (let j = start; j <= end; j++) {
        out[j] = 0;
      }
    }
  }
  return out;
}

/**
 * During gear changes the telemetry briefly reports gear = 0 (neutral).
 * Replace each zero with the last known valid gear to avoid downward needles.
 */
function removeGearZeros(values: number[]): number[] {
  const out = [...values];
  let lastValid = 1; // default to 1st gear if data starts with zeros
  for (let i = 0; i < out.length; i++) {
    if (out[i] <= 0) {
      out[i] = lastValid;
    } else {
      lastValid = out[i];
    }
  }
  return out;
}

function computeStats(values: number[]): { min: number; max: number; avg: number } {
  if (values.length === 0) return { min: 0, max: 0, avg: 0 };
  let mn = values[0], mx = values[0], sum = 0;
  for (const v of values) {
    if (v < mn) mn = v;
    if (v > mx) mx = v;
    sum += v;
  }
  return { min: mn, max: mx, avg: sum / values.length };
}

function formatStatValue(value: number, label: string): string {
  switch (label) {
    case 'Acelerador / Freno': return `${value.toFixed(0)}%`;
    case 'Marcha':             return `${Math.round(value)}ª`;
    case 'RPM':                return value >= 1000 ? `${(value / 1000).toFixed(1)}k` : value.toFixed(0);
    case 'Velocidad':          return `${value.toFixed(0)} km/h`;
    default:                   return value.toFixed(1);
  }
}

/**
 * When sample count exceeds pixel count, reduce to one representative value per pixel
 * using the median of each bucket. Median is immune to outlier spikes: a single
 * errorneous sample (or a short burst of 10–20 bad samples) in a 50+ sample bucket
 * stays below the median and maps to ~0, eliminating needle artifacts.
 */
function downsampleToPixels(values: number[], pixelCount: number): number[] {
  const n = values.length;
  if (n <= pixelCount) return values;
  const result = new Array<number>(pixelCount);
  for (let p = 0; p < pixelCount; p++) {
    const start = Math.floor((p / pixelCount) * n);
    const end = Math.floor(((p + 1) / pixelCount) * n) - 1;
    if (start >= n) { result[p] = values[n - 1]; continue; }
    if (start > end) { result[p] = values[start]; continue; }
    // Sort a copy of the slice and take the median.
    const bucket = values.slice(start, end + 1).sort((a, b) => a - b);
    const mid = Math.floor(bucket.length / 2);
    result[p] = bucket.length % 2 === 0
      ? (bucket[mid - 1] + bucket[mid]) / 2
      : bucket[mid];
  }
  return result;
}

function buildPolylinePoints(norm: number[], innerW: number, innerH: number, n: number): string {
  if (n < 2) return '';
  const pixelCount = Math.max(2, Math.floor(innerW));
  const pts = n > pixelCount ? downsampleToPixels(norm, pixelCount) : norm;
  const m = pts.length;
  return pts
    .map((v, i) => {
      const x = PAD_LEFT + (i / (m - 1)) * innerW;
      const y = PAD_TOP + (1 - v) * innerH;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(' ');
}

export default function TelemetryCharts({ samples, onIndexChange, showCursorBar = true }: Props) {
  const [cursorIdx, setCursorIdx] = useState<number>(0);
  const { width: screenW } = Dimensions.get('window');
  const safeSamples = Array.isArray(samples) ? samples : [];
  const chartWidth = screenW - 32; // full width with small margin
  const innerW = chartWidth - PAD_LEFT - PAD_RIGHT;
  const innerH = CHART_HEIGHT - PAD_TOP - PAD_BOTTOM;
  const n = safeSamples.length;
  const lapTimeOffset = useMemo(() => {
    if (safeSamples.length === 0) return 0;
    return safeSamples.reduce((min, sample) => (sample.t < min ? sample.t : min), safeSamples[0].t);
  }, [safeSamples]);

  // Precompute per-chart normalised data once
  const chartData = useMemo(
    () =>
      CHARTS.map((cfg) => {
        const isPedalsChart = cfg.label === 'Acelerador / Freno';

        const isGearChart = cfg.label === 'Marcha';

        const series = cfg.keys.map((k) => {
          const raw = safeSamples.map((s) => finiteOrZero(s[k]));
          let transformed = isPedalsChart ? raw.map((v) => normalizePedalPercent(v)) : raw;
          if (isPedalsChart && k === 'brk') {
            transformed = removePedalArtifacts(transformed, BRAKE_ACTIVE_THRESHOLD);
          } else if (isPedalsChart && k === 'thr') {
            transformed = removePedalArtifacts(transformed, THROTTLE_ACTIVE_THRESHOLD);
          } else if (isGearChart) {
            transformed = removeGearZeros(transformed);
          }
          return smoothSeries(transformed, cfg.smoothRadius ?? 0);
        });

        let min = Number.POSITIVE_INFINITY;
        let max = Number.NEGATIVE_INFINITY;

        if (isPedalsChart) {
          min = 0;
          max = 100;
        } else {
          for (const values of series) {
            for (const value of values) {
              if (value < min) min = value;
              if (value > max) max = value;
            }
          }
          if (!Number.isFinite(min) || !Number.isFinite(max)) {
            min = 0;
            max = 1;
          }
        }

        return series.map((values) => ({
          raw: values,
          norm: normaliseToRange(values, min, max),
          min,
          max,
        }));
      }),
    [safeSamples],
  );

  // Precompute polyline points strings (expensive, cache them)
  const polylines = useMemo(
    () =>
      chartData.map((seriesArr) =>
        seriesArr.map((sd) => buildPolylinePoints(sd.norm, innerW, innerH, n)),
      ),
    [chartData, innerW, innerH, n],
  );

  const xToIndex = useCallback(
    (localX: number) => {
      const clamped = Math.max(PAD_LEFT, Math.min(localX, PAD_LEFT + innerW));
      return Math.round(((clamped - PAD_LEFT) / innerW) * (n - 1));
    },
    [innerW, n],
  );

  // Web: use onMouseMove / onMouseDown on the container div
  const handlePointerMove = useCallback(
    (localX: number) => {
      const idx = xToIndex(localX);
      setCursorIdx(idx);
      const sample = safeSamples[idx];
      if (sample) {
        onIndexChange?.(idx, sample);
      }
    },
    [xToIndex, onIndexChange, safeSamples],
  );

  if (safeSamples.length < 2) {
    return <Text style={styles.empty}>Sin datos de telemetría</Text>;
  }

  const curSample = safeSamples[cursorIdx];
  const cursorX = PAD_LEFT + (cursorIdx / (n - 1)) * innerW;

  // Grid line y positions & values for a chart
  const gridLinesForChart = (min: number, max: number) => {
    const step = (max - min) / GRID_LINES;
    return Array.from({ length: GRID_LINES + 1 }, (_, i) => ({
      value: min + step * i,
      y: PAD_TOP + (1 - i / GRID_LINES) * innerH,
    }));
  };

  return (
    <View style={styles.container}>
      {/* Cursor info bar */}
      {showCursorBar && curSample && (
        <View style={styles.cursorBar}>
          <Text style={styles.cursorBarText}>
            t = {formatCursorTimestamp(Math.max(0, curSample.t - lapTimeOffset))} &nbsp;|&nbsp; Vuelta{' '}
            <Text style={styles.cursorBarHighlight}>{curSample.lap}</Text>
            &nbsp;|&nbsp;
            <Text style={{ color: '#4fc3f7' }}>{curSample.spd.toFixed(0)} km/h</Text>
            &nbsp;&nbsp;
            <Text style={{ color: '#66bb6a' }}>{formatPedalPercent(curSample.thr)}</Text>
            &nbsp;
            <Text style={{ color: '#ef5350' }}>{formatPedalPercent(curSample.brk)}</Text>
            &nbsp;&nbsp;
            <Text style={{ color: '#ffa726' }}>{curSample.rpm.toFixed(0)} rpm</Text>
            &nbsp;&nbsp;
            <Text style={{ color: '#ce93d8' }}>{Math.round(curSample.gear)}ª</Text>
          </Text>
        </View>
      )}

      {CHARTS.map((cfg, ci) => {
        const seriesData = chartData[ci];
        if (!seriesData || seriesData.length === 0) return null;
        const grid = gridLinesForChart(seriesData[0].min, seriesData[0].max);

        return (
          <View key={cfg.label} style={styles.chartWrap}>
            {/* Chart label + stats row */}
            <View style={styles.chartLabelRow}>
              <Text style={styles.chartLabel}>{cfg.label}</Text>
              <View style={styles.chartStatsRow}>
                {seriesData.map((sd, si) => {
                  const stats = computeStats(sd.raw);
                  const fmt = (v: number) => formatStatValue(v, cfg.label);
                  return (
                    <View key={si} style={styles.chartStatGroup}>
                      {cfg.keys.length > 1 && (
                        <View style={[styles.statDot, { backgroundColor: cfg.colors[si] ?? '#aaa' }]} />
                      )}
                      <Text style={[styles.chartStatText, { color: cfg.colors[si] ?? '#888' }]}>
                        min {fmt(stats.min)}{'  '}avg {fmt(stats.avg)}{'  '}max {fmt(stats.max)}
                      </Text>
                    </View>
                  );
                })}
              </View>
            </View>

            {/* SVG chart — use a div wrapper on Web for mouse events */}
            <View
              style={[styles.chartContainer, { width: chartWidth }]}
              {...(Platform.OS === 'web'
                ? {
                    // @ts-ignore
                    onMouseMove: (e: MouseEvent) => {
                      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                      handlePointerMove(e.clientX - rect.left);
                    },
                    onMouseDown: (e: MouseEvent) => {
                      const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
                      handlePointerMove(e.clientX - rect.left);
                    },
                  }
                : {
                    onStartShouldSetResponder: () => true,
                    onResponderGrant: (e: { nativeEvent: { locationX: number } }) =>
                      handlePointerMove(e.nativeEvent.locationX),
                    onResponderMove: (e: { nativeEvent: { locationX: number } }) =>
                      handlePointerMove(e.nativeEvent.locationX),
                  })}
            >
              <Svg width={chartWidth} height={CHART_HEIGHT}>
                {/* Chart background */}
                <Rect x={PAD_LEFT} y={PAD_TOP} width={innerW} height={innerH} fill="#12122a" rx={4} />

                {/* Horizontal grid lines */}
                {grid.map((g, gi) => (
                  <React.Fragment key={gi}>
                    <Line
                      x1={PAD_LEFT}
                      y1={g.y}
                      x2={PAD_LEFT + innerW}
                      y2={g.y}
                      stroke={gi === 0 || gi === GRID_LINES ? '#2a2a3e' : '#222238'}
                      strokeWidth={gi === 0 || gi === GRID_LINES ? 1 : 0.5}
                    />
                    <SvgText
                      x={PAD_LEFT - 6}
                      y={g.y + 4}
                      textAnchor="end"
                      fill="#555"
                      fontSize={9}
                      fontFamily="monospace"
                    >
                      {g.value > 1000
                        ? `${(g.value / 1000).toFixed(1)}k`
                        : g.value > 10
                        ? g.value.toFixed(0)
                        : g.value.toFixed(2)}
                    </SvgText>
                  </React.Fragment>
                ))}

                {/* Data polylines */}
                {seriesData.map((_, si) => {
                  const pts = polylines[ci]?.[si];
                  if (!pts) return null;
                  return (
                    <Polyline
                      key={si}
                      points={pts}
                      fill="none"
                      stroke={cfg.colors[si] ?? '#fff'}
                      strokeWidth={1.8}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  );
                })}

                {/* Cursor vertical line */}
                <Line
                  x1={cursorX}
                  y1={PAD_TOP}
                  x2={cursorX}
                  y2={PAD_TOP + innerH}
                  stroke="rgba(255,255,255,0.5)"
                  strokeWidth={1}
                  strokeDasharray="3,3"
                />

                {/* Cursor dots */}
                {seriesData.map((sd, si) => {
                  const yNorm = sd.norm[cursorIdx] ?? 0;
                  const cy = PAD_TOP + (1 - yNorm) * innerH;
                  return (
                    <Circle
                      key={si}
                      cx={cursorX}
                      cy={cy}
                      r={4}
                      fill={cfg.colors[si] ?? '#fff'}
                      stroke="#fff"
                      strokeWidth={1}
                    />
                  );
                })}

                {/* X-axis label (time) at bottom */}
                <SvgText x={PAD_LEFT + innerW / 2} y={CHART_HEIGHT - 4} textAnchor="middle" fill="#444" fontSize={9}>
                  tiempo (s)
                </SvgText>
              </Svg>
            </View>
          </View>
        );
      })}

      {/* Legend row */}
      <View style={styles.legend}>
        {CHARTS.flatMap((cfg, ci) =>
          cfg.keys.map((k, si) => (
            <View key={`${ci}-${si}`} style={styles.legendItem}>
              <View style={[styles.legendDot, { backgroundColor: cfg.colors[si] }]} />
              <Text style={styles.legendText}>
                {cfg.keys.length > 1
                  ? si === 0
                    ? 'Acelerador'
                    : 'Freno'
                  : cfg.label}
              </Text>
            </View>
          )),
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#0a0a1a',
    borderRadius: 8,
    overflow: 'hidden',
    paddingBottom: 8,
  },
  cursorBar: {
    backgroundColor: '#111128',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: '#1e1e3a',
  },
  cursorBarText: {
    color: '#aaa',
    fontSize: 13,
    fontFamily: 'monospace',
  },
  cursorBarHighlight: {
    color: '#fff',
    fontWeight: 'bold',
  },
  chartWrap: {
    marginTop: 4,
  },
  chartLabelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 2,
  },
  chartLabel: {
    color: '#888',
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  chartStatsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  chartStatGroup: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
  },
  statDot: {
    width: 7,
    height: 7,
    borderRadius: 4,
  },
  chartStatText: {
    fontSize: 13,
    fontFamily: 'monospace',
  },
  chartContainer: {
    cursor: 'crosshair',
  } as object,
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
    paddingHorizontal: 16,
    paddingTop: 8,
    paddingBottom: 4,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  legendDot: {
    width: 10,
    height: 10,
    borderRadius: 5,
  },
  legendText: {
    color: '#888',
    fontSize: 12,
  },
  empty: {
    color: '#666',
    fontSize: 13,
    padding: 16,
    fontStyle: 'italic',
  },
});

