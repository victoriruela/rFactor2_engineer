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

function segmentLength(segment: GPSPoint[]): number {
  if (segment.length < 2) return 0;
  let total = 0;
  for (let i = 1; i < segment.length; i++) {
    total += distance(segment[i - 1], segment[i]);
  }
  return total;
}

function segmentStraightness(segment: GPSPoint[]): number {
  if (segment.length < 2) return 1;
  const len = segmentLength(segment);
  if (len <= 0) return 1;
  const chord = distance(segment[0], segment[segment.length - 1]);
  return chord / len;
}

function minDistanceToSegmentEndpoints(segment: GPSPoint[], target: GPSPoint[]): number {
  if (segment.length === 0 || target.length === 0) return Number.POSITIVE_INFINITY;
  const probes = [segment[0], segment[segment.length - 1]];
  let minDist = Number.POSITIVE_INFINITY;
  for (const probe of probes) {
    for (const point of target) {
      const d = distance(probe, point);
      if (d < minDist) minDist = d;
    }
  }
  return minDist;
}

function median(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  if (sorted.length % 2 === 0) {
    return (sorted[mid - 1] + sorted[mid]) / 2;
  }
  return sorted[mid];
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
    if (safeGpsPoints.length === 0) return { pointSegments: [], issueCoords: [], toX: null, toY: null };

    const finitePoints = safeGpsPoints.filter(
      (point) => Number.isFinite(point.lat) && Number.isFinite(point.lon),
    );
    if (finitePoints.length === 0) {
      return { pointSegments: [], issueCoords: [], toX: null, toY: null };
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

    const lonJumpThreshold = Math.max((lonMax - lonMin) * 0.05, 0.000001);
    const latJumpThreshold = Math.max((latMax - latMin) * 0.05, 0.000001);
    const mapDiag = Math.hypot(latMax - latMin, lonMax - lonMin);

    const stepDistances: number[] = [];
    for (let i = 1; i < sanitized.length; i++) {
      stepDistances.push(distance(sanitized[i - 1], sanitized[i]));
    }
    const medianStep = median(stepDistances);
    const anomalousStepThreshold = Math.max(medianStep * 18, mapDiag * 0.035, 0.00003);

    const segments: GPSPoint[][] = [];
    let currentSegment: GPSPoint[] = [];

    for (let i = 0; i < sanitized.length; i++) {
      const point = sanitized[i];
      const prev = currentSegment[currentSegment.length - 1];

      if (!prev) {
        currentSegment.push(point);
        continue;
      }

      const lonJump = Math.abs(point.lon - prev.lon);
      const latJump = Math.abs(point.lat - prev.lat);
      const stepJump = distance(prev, point);
      const hasAbruptJump =
        lonJump > lonJumpThreshold ||
        latJump > latJumpThreshold ||
        stepJump > anomalousStepThreshold;

      if (hasAbruptJump) {
        if (currentSegment.length > 1) {
          segments.push(currentSegment);
        }
        currentSegment = [point];
        continue;
      }

      currentSegment.push(point);
    }

    if (currentSegment.length > 1) {
      segments.push(currentSegment);
    }
    if (segments.length === 0) {
      return { pointSegments: [], issueCoords: [], toX: null, toY: null };
    }

    const lengths = segments.map((segment) => segmentLength(segment));
    const mainIndex = lengths.indexOf(Math.max(...lengths));
    const mainSegment = segments[mainIndex];
    const connectThreshold = Math.max(mapDiag * 0.055, 0.00003);

    const filteredSegments = segments.filter((segment, index) => {
      if (index === mainIndex) return true;
      if (segment.length < 3) return false;

      const startToMain = minDistanceToSegmentEndpoints([segment[0]], mainSegment);
      const endToMain = minDistanceToSegmentEndpoints([segment[segment.length - 1]], mainSegment);
      const reconnectsBothEnds = startToMain <= connectThreshold && endToMain <= connectThreshold;
      if (reconnectsBothEnds) return true;

      const len = lengths[index];
      const isLongChunk = len >= lengths[mainIndex] * 0.35;
      if (isLongChunk) return true;

      const straightness = segmentStraightness(segment);
      const isIsolatedStraightArtifact = straightness > 0.975 && len < mapDiag * 0.45;
      return !isIsolatedStraightArtifact;
    });

    const drawingSegments = filteredSegments.length > 0 ? filteredSegments : [mainSegment];
    const drawingPoints = drawingSegments.flat();
    if (drawingPoints.length === 0) {
      return { pointSegments: [], issueCoords: [], toX: null, toY: null };
    }

    const pad = 20;
    let minLat = drawingPoints[0].lat;
    let maxLat = drawingPoints[0].lat;
    let minLon = drawingPoints[0].lon;
    let maxLon = drawingPoints[0].lon;
    for (const point of drawingPoints) {
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

    const pointsSegmentsStr = drawingSegments.map((segment) =>
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
