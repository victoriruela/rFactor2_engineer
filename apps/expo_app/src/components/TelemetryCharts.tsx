/**
 * TelemetryCharts — interactive telemetry viewer.
 * Shows Speed / Throttle+Brake / RPM as SVG line charts.
 * A draggable vertical cursor moves across all three charts simultaneously.
 */
import React, { useCallback, useMemo, useState } from 'react';
import { View, Text, StyleSheet, GestureResponderEvent, Dimensions } from 'react-native';
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
}

const CHART_HEIGHT = 120;
const PAD_LEFT = 40;
const PAD_RIGHT = 12;
const PAD_TOP = 12;
const PAD_BOTTOM = 24;

interface ChartConfig {
  label: string;
  keys: Array<keyof TelemetrySample>;
  colors: string[];
  unit: string;
}

const CHARTS: ChartConfig[] = [
  { label: 'Velocidad (km/h)', keys: ['spd'], colors: ['#4fc3f7'], unit: 'km/h' },
  { label: 'Acelerador / Freno (%)', keys: ['thr', 'brk'], colors: ['#66bb6a', '#ef5350'], unit: '%' },
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
  if (normalised.length < 2) return '';
  return normalised
    .map((v, i) => {
      const x = PAD_LEFT + (i / (normalised.length - 1)) * innerW;
      const y = PAD_TOP + (1 - v) * innerH;
      return `${Math.round(x)},${Math.round(y)}`;
    })
    .join(' ');
}

function formatValue(v: number, unit: string): string {
  if (unit === '%') return `${Math.round(v * 100)}%`;
  if (unit === 'rpm') return `${Math.round(v)}`;
  return `${v.toFixed(1)}`;
}

export default function TelemetryCharts({ samples, onIndexChange }: Props) {
  const [cursorIdx, setCursorIdx] = useState<number>(0);
  const screenWidth = Dimensions.get('window').width;
  const width = Math.min(screenWidth - 32, 800); // responsive width with padding
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

  const handlePointerEvent = useCallback(
    (evt: GestureResponderEvent) => {
      const localX = evt.nativeEvent.locationX;
      const idx = xToIndex(localX);
      setCursorIdx(idx);
      onIndexChange?.(idx);
    },
    [xToIndex, onIndexChange],
  );

  if (!samples || samples.length < 2) {
    return <Text style={styles.empty}>Sin datos de telemetría</Text>;
  }

  const cursorX = PAD_LEFT + (cursorIdx / (n - 1)) * innerW;

  return (
    <View style={styles.container}>
      {CHARTS.map((cfg, ci) => {
        const seriesData = chartData[ci];
        if (!seriesData || seriesData.length === 0) return null;

        const curVal = samples[cursorIdx]?.[cfg.keys[0]] as number | undefined;

        return (
          <View key={cfg.label} style={styles.chartWrap}>
            <View style={styles.chartHeader}>
              <Text style={styles.chartLabel}>{cfg.label}</Text>
              {curVal != null && (
                <Text style={[styles.cursorVal, { color: cfg.colors[0] }]}>
                  {formatValue(curVal, cfg.unit)}
                </Text>
              )}
            </View>

            <View
              style={styles.chartContainer}
              onStartShouldSetResponder={() => true}
              onResponderGrant={handlePointerEvent}
              onResponderMove={handlePointerEvent}
            >
              <Svg width={width} height={CHART_HEIGHT}>
                {/* Background */}
                <Rect
                  x={PAD_LEFT}
                  y={PAD_TOP}
                  width={innerW}
                  height={innerH}
                  fill="#1a1a2e"
                  rx={3}
                />

                {/* Grid lines */}
                <Line x1={PAD_LEFT} y1={PAD_TOP + innerH / 2} x2={PAD_LEFT + innerW} y2={PAD_TOP + innerH / 2} stroke="#333" strokeWidth={0.5} />

                {/* Y-axis labels */}
                <SvgText
                  x={PAD_LEFT - 6}
                  y={PAD_TOP + 8}
                  textAnchor="end"
                  fill="#666"
                  fontSize={10}
                  fontFamily="monospace"
                >
                  {seriesData[0]?.max.toFixed(seriesData[0].max > 10 ? 0 : 1)}
                </SvgText>
                <SvgText
                  x={PAD_LEFT - 6}
                  y={PAD_TOP + innerH + 4}
                  textAnchor="end"
                  fill="#666"
                  fontSize={10}
                  fontFamily="monospace"
                >
                  {seriesData[0]?.min.toFixed(seriesData[0].min > 10 ? 0 : 1)}
                </SvgText>

                {/* Data lines */}
                {seriesData.map((sd, si) => {
                  const pts = buildPoints(sd.norm, innerW, innerH);
                  if (!pts) return null;
                  return (
                    <Polyline
                      key={si}
                      points={pts}
                      fill="none"
                      stroke={cfg.colors[si] ?? '#fff'}
                      strokeWidth={2}
                      strokeLinejoin="round"
                      strokeLinecap="round"
                    />
                  );
                })}

                {/* Cursor line */}
                <Line
                  x1={cursorX}
                  y1={PAD_TOP}
                  x2={cursorX}
                  y2={PAD_TOP + innerH}
                  stroke="#fff"
                  strokeWidth={1.5}
                  opacity={0.7}
                />

                {/* Cursor dot at data point */}
                {seriesData[0] && (
                  <circle
                    cx={cursorX}
                    cy={PAD_TOP + (1 - seriesData[0].norm[cursorIdx]) * innerH}
                    r={3}
                    fill="#fff"
                    opacity={0.8}
                  />
                )}
              </Svg>
            </View>
          </View>
        );
      })}

      {/* Time and lap label */}
      {cursorIdx != null && samples[cursorIdx] && (
        <Text style={styles.timeLabel}>
          t = {samples[cursorIdx].t.toFixed(2)}s  |  Vuelta {samples[cursorIdx].lap}
        </Text>
      )}

      {/* Legend */}
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
    backgroundColor: '#0d0d1f',
    borderRadius: 8,
    padding: 12,
    gap: 12,
    width: '100%',
    alignItems: 'center',
  },
  chartWrap: {
    width: '100%',
    gap: 6,
  },
  chartHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingHorizontal: 4,
    marginBottom: 4,
  },
  chartLabel: {
    color: '#888',
    fontSize: 12,
    fontWeight: '600',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  cursorVal: {
    fontSize: 13,
    fontWeight: '700',
  },
  chartContainer: {
    backgroundColor: '#111',
    borderRadius: 6,
    overflow: 'hidden',
    borderWidth: 1,
    borderColor: '#222',
  },
  empty: {
    color: '#666',
    fontSize: 13,
    fontStyle: 'italic',
  },
  timeLabel: {
    color: '#888',
    fontSize: 11,
    textAlign: 'center',
    marginTop: 8,
    fontFamily: 'monospace',
  },
  legend: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
    justifyContent: 'center',
    paddingHorizontal: 4,
    marginTop: 8,
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
    color: '#999',
    fontSize: 11,
  },
});

