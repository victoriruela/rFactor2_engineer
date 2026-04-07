/**
 * TelemetryCharts — interactive telemetry viewer.
 * Shows Speed / Throttle+Brake / RPM as SVG line charts.
 * A draggable vertical cursor moves across all three charts simultaneously and
 * drives the position marker on the parent's CircuitMap via onIndexChange.
 */
import React, { useCallback, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, PanResponder } from 'react-native';
import Svg, {
  Line,
  Polyline,
  Rect,
  Text as SvgText,
} from 'react-native-svg';
import type { TelemetrySample } from '../api';

interface Props {
  samples: TelemetrySample[];
  onIndexChange?: (index: number) => void;
  width?: number;
}

const CHART_HEIGHT = 100;
const PAD_LEFT = 36;
const PAD_RIGHT = 8;
const PAD_TOP = 8;
const PAD_BOTTOM = 20;

interface ChartConfig {
  label: string;
  keys: Array<keyof TelemetrySample>;
  colors: string[];
  unit: string;
}

const CHARTS: ChartConfig[] = [
  { label: 'Velocidad', keys: ['spd'], colors: ['#4fc3f7'], unit: 'km/h' },
  { label: 'Acelerador / Freno', keys: ['thr', 'brk'], colors: ['#66bb6a', '#ef5350'], unit: '%' },
  { label: 'RPM', keys: ['rpm'], colors: ['#ffa726'], unit: 'rpm' },
];

function normalise(values: number[]): number[] {
  const mn = Math.min(...values);
  const mx = Math.max(...values);
  const range = mx - mn || 1;
  return values.map((v) => (v - mn) / range);
}

function buildPoints(
  normalised: number[],
  innerW: number,
  innerH: number,
): string {
  return normalised
    .map((v, i) => {
      const x = PAD_LEFT + (i / (normalised.length - 1)) * innerW;
      const y = PAD_TOP + (1 - v) * innerH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

function formatValue(v: number, unit: string): string {
  if (unit === '%') return `${(v * 100).toFixed(0)}%`;
  if (unit === 'rpm') return `${Math.round(v)}`;
  return `${v.toFixed(1)}`;
}

export default function TelemetryCharts({ samples, onIndexChange, width = 700 }: Props) {
  const [cursorX, setCursorX] = useState<number | null>(null);
  const [cursorIdx, setCursorIdx] = useState<number>(0);
  const containerRef = useRef<View>(null);
  const containerLeft = useRef<number>(0);

  const innerW = width - PAD_LEFT - PAD_RIGHT;
  const innerH = CHART_HEIGHT - PAD_TOP - PAD_BOTTOM;

  const n = samples.length;

  // Precompute per-chart data
  const chartData = useMemo(
    () =>
      CHARTS.map((cfg) =>
        cfg.keys.map((k) => {
          const raw = samples.map((s) => (s[k] as number) ?? 0);
          return {
            raw,
            norm: normalise(raw),
            min: Math.min(...raw),
            max: Math.max(...raw),
          };
        }),
      ),
    [samples],
  );

  const xToIndex = useCallback(
    (localX: number) => {
      const clamped = Math.max(PAD_LEFT, Math.min(localX, PAD_LEFT + innerW));
      return Math.round(((clamped - PAD_LEFT) / innerW) * (n - 1));
    },
    [innerW, n],
  );

  const panResponder = useMemo(
    () =>
      PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: (evt) => {
          const localX = evt.nativeEvent.locationX;
          const idx = xToIndex(localX);
          setCursorX(PAD_LEFT + (idx / (n - 1)) * innerW);
          setCursorIdx(idx);
          onIndexChange?.(idx);
        },
        onPanResponderMove: (evt) => {
          const localX = evt.nativeEvent.locationX;
          const idx = xToIndex(localX);
          setCursorX(PAD_LEFT + (idx / (n - 1)) * innerW);
          setCursorIdx(idx);
          onIndexChange?.(idx);
        },
      }),
    [xToIndex, innerW, n, onIndexChange],
  );

  if (!samples || samples.length < 2) {
    return null;
  }

  return (
    <View style={styles.container}>
      {CHARTS.map((cfg, ci) => {
        const seriesData = chartData[ci];
        const curVal =
          cursorIdx != null && cfg.keys[0] ? samples[cursorIdx]?.[cfg.keys[0]] : undefined;

        return (
          <View key={cfg.label} style={styles.chartWrap}>
            <View style={styles.chartHeader}>
              <Text style={styles.chartLabel}>{cfg.label}</Text>
              {curVal != null && (
                <Text style={[styles.cursorVal, { color: cfg.colors[0] }]}>
                  {formatValue(curVal as number, cfg.unit)} {cfg.unit}
                </Text>
              )}
            </View>

            <View {...panResponder.panHandlers}>
              <Svg width={width} height={CHART_HEIGHT}>
                {/* Background */}
                <Rect
                  x={PAD_LEFT}
                  y={PAD_TOP}
                  width={innerW}
                  height={innerH}
                  fill="#1a1a2e"
                  rx={2}
                />

                {/* Y-axis labels */}
                <SvgText
                  x={PAD_LEFT - 4}
                  y={PAD_TOP + 4}
                  textAnchor="end"
                  fill="#666"
                  fontSize={9}
                >
                  {seriesData[0]?.max.toFixed(seriesData[0].max > 10 ? 0 : 1)}
                </SvgText>
                <SvgText
                  x={PAD_LEFT - 4}
                  y={PAD_TOP + innerH}
                  textAnchor="end"
                  fill="#666"
                  fontSize={9}
                >
                  {seriesData[0]?.min.toFixed(seriesData[0].min > 10 ? 0 : 1)}
                </SvgText>

                {/* Data lines */}
                {seriesData.map((sd, si) => (
                  <Polyline
                    key={si}
                    points={buildPoints(sd.norm, innerW, innerH)}
                    fill="none"
                    stroke={cfg.colors[si] ?? '#fff'}
                    strokeWidth={1.5}
                    strokeLinejoin="round"
                  />
                ))}

                {/* Cursor line */}
                {cursorX != null && (
                  <Line
                    x1={cursorX}
                    y1={PAD_TOP}
                    x2={cursorX}
                    y2={PAD_TOP + innerH}
                    stroke="#fff"
                    strokeWidth={1}
                    strokeDasharray="4,3"
                    opacity={0.6}
                  />
                )}
              </Svg>
            </View>
          </View>
        );
      })}

      {/* Time label */}
      {cursorIdx != null && samples[cursorIdx] && (
        <Text style={styles.timeLabel}>
          t = {samples[cursorIdx].t.toFixed(2)} s — Vuelta {samples[cursorIdx].lap}
        </Text>
      )}

      {/* Legend for throttle/brake chart */}
      <View style={styles.legend}>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: '#4fc3f7' }]} />
          <Text style={styles.legendText}>Velocidad</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: '#66bb6a' }]} />
          <Text style={styles.legendText}>Acelerador</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: '#ef5350' }]} />
          <Text style={styles.legendText}>Freno</Text>
        </View>
        <View style={styles.legendItem}>
          <View style={[styles.legendDot, { backgroundColor: '#ffa726' }]} />
          <Text style={styles.legendText}>RPM</Text>
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#111',
    borderRadius: 8,
    padding: 8,
    gap: 12,
  },
  chartWrap: {
    gap: 4,
  },
  chartHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
  },
  chartLabel: {
    color: '#888',
    fontSize: 11,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  cursorVal: {
    fontSize: 12,
    fontWeight: '600',
  },
  timeLabel: {
    color: '#666',
    fontSize: 11,
    textAlign: 'center',
  },
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    paddingHorizontal: 4,
    paddingTop: 4,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  legendDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
  },
  legendText: {
    color: '#888',
    fontSize: 11,
  },
});
