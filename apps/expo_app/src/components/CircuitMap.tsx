import React, { useMemo } from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, { Polyline, Circle } from 'react-native-svg';
import type { GPSPoint, IssueMarker } from '../api';

interface Props {
  gpsPoints: GPSPoint[] | null | undefined;
  issues?: IssueMarker[] | null;
  /** GPS point of the current cursor position from TelemetryCharts */
  currentPosition?: GPSPoint | null;
  width?: number;
  height?: number;
}

const SEVERITY_COLORS: Record<string, string> = {
  high: '#f44336',
  medium: '#ff9800',
  low: '#ffc107',
};

export default function CircuitMap({ gpsPoints, issues = [], currentPosition, width = 700, height = 400 }: Props) {
  const safeGpsPoints = Array.isArray(gpsPoints) ? gpsPoints : [];
  const safeIssues = Array.isArray(issues) ? issues : [];

  const { points, issueCoords, toX, toY } = useMemo(() => {
    if (safeGpsPoints.length === 0) return { points: '', issueCoords: [], toX: null, toY: null };

    const finitePoints = safeGpsPoints.filter(
      (point) => Number.isFinite(point.lat) && Number.isFinite(point.lon),
    );
    if (finitePoints.length === 0) {
      return { points: '', issueCoords: [], toX: null, toY: null };
    }

    const sanitized: GPSPoint[] = [];
    for (let i = 0; i < finitePoints.length; i++) {
      const curr = finitePoints[i];
      const prev = sanitized[sanitized.length - 1];
      if (!prev || prev.lat !== curr.lat || prev.lon !== curr.lon) {
        sanitized.push(curr);
      }
    }
    if (sanitized.length === 0) {
      return { points: '', issueCoords: [], toX: null, toY: null };
    }

    const pad = 20;
    let minLat = sanitized[0].lat;
    let maxLat = sanitized[0].lat;
    let minLon = sanitized[0].lon;
    let maxLon = sanitized[0].lon;
    for (const point of sanitized) {
      if (point.lat < minLat) minLat = point.lat;
      if (point.lat > maxLat) maxLat = point.lat;
      if (point.lon < minLon) minLon = point.lon;
      if (point.lon > maxLon) maxLon = point.lon;
    }

    const rangeX = maxLon - minLon || 1;
    const rangeY = maxLat - minLat || 1;
    const scaleX = (width - 2 * pad) / rangeX;
    const scaleY = (height - 2 * pad) / rangeY;
    const scale = Math.min(scaleX, scaleY);
    const contentW = rangeX * scale;
    const contentH = rangeY * scale;
    const offsetX = (width - contentW) / 2;
    const offsetY = (height - contentH) / 2;

    const toXFn = (lon: number) => offsetX + (lon - minLon) * scale;
    const toYFn = (lat: number) => height - (offsetY + (lat - minLat) * scale);

    const pointsStr = sanitized
      .map((point) => `${toXFn(point.lon)},${toYFn(point.lat)}`)
      .join(' ');

    const ic = safeIssues.map((m) => ({
      x: toXFn(m.lon),
      y: toYFn(m.lat),
      color: SEVERITY_COLORS[m.severity] ?? '#ff9800',
      desc: m.description,
    }));

    return { points: pointsStr, issueCoords: ic, toX: toXFn, toY: toYFn };
  }, [safeGpsPoints, safeIssues, width, height]);

  if (safeGpsPoints.length === 0) return null;

  const posX = currentPosition && toX ? toX(currentPosition.lon) : null;
  const posY = currentPosition && toY ? toY(currentPosition.lat) : null;

  return (
    <View style={styles.container}>
      <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        {points ? <Polyline points={points} fill="none" stroke="#4fc3f7" strokeWidth={2} /> : null}
        {issueCoords.map((ic, i) => (
          <Circle key={i} cx={ic.x} cy={ic.y} r={6} fill={ic.color} opacity={0.8} />
        ))}
        {/* Moving position marker */}
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
