import React, { useMemo } from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, { Circle, Line } from 'react-native-svg';
import type { GPSPoint, IssueMarker, TelemetrySample } from '../api';

interface Props {
  gpsPoints: GPSPoint[] | null | undefined;
  telemetrySamples?: TelemetrySample[] | null;
  issues?: IssueMarker[] | null;
  currentPosition?: GPSPoint | null;
  width?: number;
  height?: number;
}

interface StrokeSegment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color: string;
}

function distance(a: GPSPoint, b: GPSPoint): number {
  return Math.hypot(a.lat - b.lat, a.lon - b.lon);
}

const SEVERITY_COLORS: Record<string, string> = {
  high: '#f44336',
  medium: '#ff9800',
  low: '#ffc107',
};

const BASE_TRACK_GREEN = '#66bb6a';
const BRAKE_RED = '#ff3b30';
const WHITE = '#ffffff';

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.max(0, Math.min(1, value));
}

function normalizePedal(value: number): number {
  const normalized = Math.abs(value) <= 1 ? value : value / 100;
  return clamp01(normalized);
}

function movingAverage(values: number[], radius: number): number[] {
  if (values.length === 0 || radius <= 0) return values;
  const out = new Array(values.length).fill(0);
  for (let i = 0; i < values.length; i++) {
    let sum = 0;
    let count = 0;
    const start = Math.max(0, i - radius);
    const end = Math.min(values.length - 1, i + radius);
    for (let j = start; j <= end; j++) {
      sum += values[j];
      count++;
    }
    out[i] = count > 0 ? sum / count : values[i];
  }
  return out;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const clean = hex.replace('#', '');
  const value = clean.length === 3
    ? clean.split('').map((c) => `${c}${c}`).join('')
    : clean;
  const num = Number.parseInt(value, 16);
  return {
    r: (num >> 16) & 255,
    g: (num >> 8) & 255,
    b: num & 255,
  };
}

function mixColor(from: string, to: string, amount: number): string {
  const t = clamp01(amount);
  const a = hexToRgb(from);
  const b = hexToRgb(to);
  const r = Math.round(a.r + (b.r - a.r) * t);
  const g = Math.round(a.g + (b.g - a.g) * t);
  const bl = Math.round(a.b + (b.b - a.b) * t);
  return `rgb(${r}, ${g}, ${bl})`;
}

export default function CircuitMap({
  gpsPoints,
  telemetrySamples = [],
  issues = [],
  currentPosition,
  width = 700,
  height = 400,
}: Props) {
  const safeGpsPoints = Array.isArray(gpsPoints) ? gpsPoints : [];
  const safeTelemetry = Array.isArray(telemetrySamples) ? telemetrySamples : [];
  const safeIssues = Array.isArray(issues) ? issues : [];

  const { strokeSegments, issueCoords, toX, toY } = useMemo(() => {
    const finitePoints = safeGpsPoints.filter(
      (point) => Number.isFinite(point.lat) && Number.isFinite(point.lon),
    );
    if (finitePoints.length < 2) {
      return { strokeSegments: [], issueCoords: [], toX: null, toY: null };
    }

    const sanitized: GPSPoint[] = [];
    for (const point of finitePoints) {
      const prev = sanitized[sanitized.length - 1];
      if (!prev || prev.lat !== point.lat || prev.lon !== point.lon) {
        sanitized.push(point);
      }
    }
    if (sanitized.length < 2) {
      return { strokeSegments: [], issueCoords: [], toX: null, toY: null };
    }

    let lonMin = sanitized[0].lon;
    let lonMax = sanitized[0].lon;
    let latMin = sanitized[0].lat;
    let latMax = sanitized[0].lat;
    for (const point of sanitized) {
      if (point.lon < lonMin) lonMin = point.lon;
      if (point.lon > lonMax) lonMax = point.lon;
      if (point.lat < latMin) latMin = point.lat;
      if (point.lat > latMax) latMax = point.lat;
    }

    const rangeX = lonMax - lonMin || 1;
    const rangeY = latMax - latMin || 1;
    const mapDiag = Math.hypot(rangeX, rangeY);
    const pad = 20;
    const scaleX = (width - 2 * pad) / rangeX;
    const scaleY = (height - 2 * pad) / rangeY;
    const scale = Math.min(scaleX, scaleY);
    const contentW = rangeX * scale;
    const contentH = rangeY * scale;
    const offsetX = (width - contentW) / 2;
    const offsetY = (height - contentH) / 2;

    const toXFn = (lon: number) => offsetX + (lon - lonMin) * scale;
    const toYFn = (lat: number) => height - (offsetY + (lat - latMin) * scale);

    const telemetryWithGps = safeTelemetry.filter(
      (sample) =>
        Number.isFinite(sample.lat) &&
        Number.isFinite(sample.lon) &&
        Number.isFinite(sample.thr) &&
        Number.isFinite(sample.brk),
    );

    const telemetryBrake = telemetryWithGps.length > 0
      ? movingAverage(
          sanitized.map((_, idx) => {
            const sourceIdx = Math.round((idx / Math.max(sanitized.length - 1, 1)) * (telemetryWithGps.length - 1));
            return normalizePedal(telemetryWithGps[sourceIdx]?.brk ?? 0);
          }),
          2,
        )
      : new Array(sanitized.length).fill(0);

    const telemetryThrottle = telemetryWithGps.length > 0
      ? movingAverage(
          sanitized.map((_, idx) => {
            const sourceIdx = Math.round((idx / Math.max(sanitized.length - 1, 1)) * (telemetryWithGps.length - 1));
            return normalizePedal(telemetryWithGps[sourceIdx]?.thr ?? 0);
          }),
          2,
        )
      : new Array(sanitized.length).fill(0);

    // With single-lap data from backend, discontinuities should be rare.
    // Break only on truly anomalous jumps (> 5% of coordinate range, matching Python lap_xy).
    const maxJump = Math.max(mapDiag * 0.05, 0.001);
    const segments: StrokeSegment[] = [];
    for (let i = 1; i < sanitized.length; i++) {
      const from = sanitized[i - 1];
      const to = sanitized[i];
      if (distance(from, to) > maxJump) continue;

      const brakeIntensity = (telemetryBrake[i - 1] + telemetryBrake[i]) * 0.5;
      const throttleLevel = clamp01((telemetryThrottle[i - 1] + telemetryThrottle[i]) * 0.5);

      // 100% throttle => green, 0% throttle => white.
      // Using a slight gamma (< 1) makes the whitening more visible in mid-low throttle.
      let strokeColor = mixColor(WHITE, BASE_TRACK_GREEN, Math.pow(throttleLevel, 0.75));
      if (brakeIntensity > 0.02) {
        // Boost and lower gamma so red pops earlier and looks more vivid.
        const boostedBrake = clamp01(brakeIntensity * 1.2);
        strokeColor = mixColor(WHITE, BRAKE_RED, Math.pow(boostedBrake, 0.5));
      }

      segments.push({
        x1: toXFn(from.lon),
        y1: toYFn(from.lat),
        x2: toXFn(to.lon),
        y2: toYFn(to.lat),
        color: strokeColor,
      });
    }

    if (segments.length === 0) {
      return { strokeSegments: [], issueCoords: [], toX: null, toY: null };
    }

    const ic = safeIssues.map((m) => ({
      x: toXFn(m.lon),
      y: toYFn(m.lat),
      color: SEVERITY_COLORS[m.severity] ?? '#ff9800',
      desc: m.description,
    }));

    return { strokeSegments: segments, issueCoords: ic, toX: toXFn, toY: toYFn };
  }, [safeGpsPoints, safeIssues, safeTelemetry, width, height]);

  if (safeGpsPoints.length === 0) return null;

  const posX = currentPosition && toX ? toX(currentPosition.lon) : null;
  const posY = currentPosition && toY ? toY(currentPosition.lat) : null;

  return (
    <View style={styles.container}>
      <View style={[styles.canvasFrame, { width, height }]}>
        <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
          {strokeSegments.map((segment, index) => (
            <Line
              key={index}
              x1={segment.x1}
              y1={segment.y1}
              x2={segment.x2}
              y2={segment.y2}
              stroke={segment.color}
              strokeWidth={7.5}
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}
          {issueCoords.map((ic, i) => (
            <Circle key={i} cx={ic.x} cy={ic.y} r={6} fill={ic.color} opacity={0.8} />
          ))}
          {posX != null && posY != null && (
            <>
              <Circle cx={posX} cy={posY} r={10} fill="none" stroke="#fff" strokeWidth={1.5} opacity={0.5} />
              <Circle cx={posX} cy={posY} r={5} fill="#fff" opacity={0.9} />
            </>
          )}
        </Svg>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    width: '100%',
    alignItems: 'center',
  },
  canvasFrame: {
    backgroundColor: '#111',
    borderRadius: 8,
    overflow: 'hidden',
  },
});
