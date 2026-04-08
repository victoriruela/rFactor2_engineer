import React, { useMemo } from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, { Polyline, Circle } from 'react-native-svg';
import type { GPSPoint, IssueMarker } from '../api';

interface Props {
  gpsPoints: GPSPoint[] | null | undefined;
  issues?: IssueMarker[] | null;
  currentPosition?: GPSPoint | null;
  width?: number;
  height?: number;
}

function distance(a: GPSPoint, b: GPSPoint): number {
  return Math.hypot(a.lat - b.lat, a.lon - b.lon);
}

const SEVERITY_COLORS: Record<string, string> = {
  high: '#f44336',
  medium: '#ff9800',
  low: '#ffc107',
};

export default function CircuitMap({ gpsPoints, issues = [], currentPosition, width = 700, height = 400 }: Props) {
  const safeGpsPoints = Array.isArray(gpsPoints) ? gpsPoints : [];
  const safeIssues = Array.isArray(issues) ? issues : [];

  const { pointSegments, issueCoords, toX, toY } = useMemo(() => {
    const finitePoints = safeGpsPoints.filter(
      (point) => Number.isFinite(point.lat) && Number.isFinite(point.lon),
    );
    if (finitePoints.length < 2) {
      return { pointSegments: [], issueCoords: [], toX: null, toY: null };
    }

    const sanitized: GPSPoint[] = [];
    for (const point of finitePoints) {
      const prev = sanitized[sanitized.length - 1];
      if (!prev || prev.lat !== point.lat || prev.lon !== point.lon) {
        sanitized.push(point);
      }
    }
    if (sanitized.length < 2) {
      return { pointSegments: [], issueCoords: [], toX: null, toY: null };
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

    // With single-lap data from backend, discontinuities should be rare.
    // Break only on truly anomalous jumps (> 5% of coordinate range, matching Python lap_xy).
    const maxJump = Math.max(mapDiag * 0.05, 0.001);
    const segments: GPSPoint[][] = [];
    let currentSegment: GPSPoint[] = [sanitized[0]];
    for (let i = 1; i < sanitized.length; i++) {
      const point = sanitized[i];
      const prev = currentSegment[currentSegment.length - 1];
      if (distance(prev, point) > maxJump) {
        if (currentSegment.length > 1) {
          segments.push(currentSegment);
        }
        currentSegment = [point];
      } else {
        currentSegment.push(point);
      }
    }
    if (currentSegment.length > 1) {
      segments.push(currentSegment);
    }
    if (segments.length === 0) {
      return { pointSegments: [], issueCoords: [], toX: null, toY: null };
    }

    const pointsSegmentsStr = segments.map((segment) =>
      segment.map((point) => `${toXFn(point.lon)},${toYFn(point.lat)}`).join(' '),
    );

    const ic = safeIssues.map((m) => ({
      x: toXFn(m.lon),
      y: toYFn(m.lat),
      color: SEVERITY_COLORS[m.severity] ?? '#ff9800',
      desc: m.description,
    }));

    return { pointSegments: pointsSegmentsStr, issueCoords: ic, toX: toXFn, toY: toYFn };
  }, [safeGpsPoints, safeIssues, width, height]);

  if (safeGpsPoints.length === 0) return null;

  const posX = currentPosition && toX ? toX(currentPosition.lon) : null;
  const posY = currentPosition && toY ? toY(currentPosition.lat) : null;

  return (
    <View style={styles.container}>
      <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {pointSegments.map((segmentPoints, index) => (
          <Polyline key={index} points={segmentPoints} fill="none" stroke="#4fc3f7" strokeWidth={2} />
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
  );
}

const styles = StyleSheet.create({
  container: {
    backgroundColor: '#111',
    borderRadius: 8,
    overflow: 'hidden',
  },
});
