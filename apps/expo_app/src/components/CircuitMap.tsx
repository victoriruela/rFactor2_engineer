import React, { useMemo } from 'react';
import { View, StyleSheet } from 'react-native';
import Svg, { Polyline, Circle } from 'react-native-svg';
import type { GPSPoint, IssueMarker } from '../api';

interface Props {
  gpsPoints: GPSPoint[];
  issues?: IssueMarker[];
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
  const { points, issueCoords, toX, toY } = useMemo(() => {
    if (gpsPoints.length === 0) return { points: '', issueCoords: [], toX: null, toY: null };

    const pad = 20;
    const lats = gpsPoints.map((p) => p.lat);
    const lons = gpsPoints.map((p) => p.lon);
    const minLat = Math.min(...lats);
    const maxLat = Math.max(...lats);
    const minLon = Math.min(...lons);
    const maxLon = Math.max(...lons);

    const rangeX = maxLon - minLon || 1;
    const rangeY = maxLat - minLat || 1;
    const scaleX = (width - 2 * pad) / rangeX;
    const scaleY = (height - 2 * pad) / rangeY;

    const toXFn = (lon: number) => pad + (lon - minLon) * scaleX;
    const toYFn = (lat: number) => height - pad - (lat - minLat) * scaleY;

    const pts = gpsPoints.map((p) => `${toXFn(p.lon)},${toYFn(p.lat)}`).join(' ');

    const ic = issues.map((m) => ({
      x: toXFn(m.lon),
      y: toYFn(m.lat),
      color: SEVERITY_COLORS[m.severity] ?? '#ff9800',
      desc: m.description,
    }));

    return { points: pts, issueCoords: ic, toX: toXFn, toY: toYFn };
  }, [gpsPoints, issues, width, height]);

  if (gpsPoints.length === 0) return null;

  const posX = currentPosition && toX ? toX(currentPosition.lon) : null;
  const posY = currentPosition && toY ? toY(currentPosition.lat) : null;

  return (
    <View style={styles.container}>
      <Svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
        <Polyline points={points} fill="none" stroke="#4fc3f7" strokeWidth={2} />
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
