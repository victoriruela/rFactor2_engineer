import { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, useWindowDimensions, Pressable } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import type { GPSPoint, TelemetrySample } from '../../src/api';
import CircuitMap from '../../src/components/CircuitMap';
import TelemetryCharts, { type ChartConfig } from '../../src/components/TelemetryCharts';

const CORNER_COLORS = ['#4fc3f7', '#ff8a65', '#81c784', '#ce93d8'];
const CORNER_LABELS = ['FL', 'FR', 'RL', 'RR'];

const CHART_TABS = ['Conducción', 'Neumáticos', 'Suspensión', 'Frenos', 'Motor', 'Dirección'] as const;
type ChartTab = typeof CHART_TABS[number];

const TAB_CHARTS: Record<ChartTab, ChartConfig[]> = {
  'Conducción': [
    { label: 'Velocidad',          keys: ['spd'],              colors: ['#4fc3f7'],             unit: 'km/h', smoothRadius: 2 },
    { label: 'Acelerador / Freno', keys: ['thr', 'brk'],       colors: ['#66bb6a', '#ef5350'],  unit: '%',    smoothRadius: 1 },
    { label: 'RPM',                keys: ['rpm'],              colors: ['#ffa726'],             unit: 'rpm',  smoothRadius: 2 },
    { label: 'Marcha',             keys: ['gear'],             colors: ['#ce93d8'],             unit: '',     smoothRadius: 0 },
  ],
  'Neumáticos': [
    { label: 'Temp. Neumático',    keys: ['tyre_t_fl', 'tyre_t_fr', 'tyre_t_rl', 'tyre_t_rr'],       colors: CORNER_COLORS, seriesLabels: CORNER_LABELS, unit: '°C',   smoothRadius: 3 },
    { label: 'Presión Neumático',  keys: ['tyre_p_fl', 'tyre_p_fr', 'tyre_p_rl', 'tyre_p_rr'],       colors: CORNER_COLORS, seriesLabels: CORNER_LABELS, unit: 'kPa',  smoothRadius: 3 },
    { label: 'Desgaste Neumático', keys: ['tyre_w_fl', 'tyre_w_fr', 'tyre_w_rl', 'tyre_w_rr'],       colors: CORNER_COLORS, seriesLabels: CORNER_LABELS, unit: '',     smoothRadius: 2 },
    { label: 'Carga Neumático',    keys: ['tyre_l_fl', 'tyre_l_fr', 'tyre_l_rl', 'tyre_l_rr'],       colors: CORNER_COLORS, seriesLabels: CORNER_LABELS, unit: 'N',    smoothRadius: 2 },
    { label: 'Grip Fraction',      keys: ['grip_fl', 'grip_fr', 'grip_rl', 'grip_rr'],               colors: CORNER_COLORS, seriesLabels: CORNER_LABELS, unit: '',     smoothRadius: 2 },
    { label: 'Vel. Rueda',         keys: ['wheel_sp_fl', 'wheel_sp_fr', 'wheel_sp_rl', 'wheel_sp_rr'], colors: CORNER_COLORS, seriesLabels: CORNER_LABELS, unit: 'rad/s', smoothRadius: 2 },
  ],
  'Suspensión': [
    { label: 'Altura Suspensión',      keys: ['ride_h_fl', 'ride_h_fr', 'ride_h_rl', 'ride_h_rr'], colors: CORNER_COLORS, seriesLabels: CORNER_LABELS, unit: 'mm', smoothRadius: 2 },
    { label: 'G-Fuerza Lateral',       keys: ['g_lat'],  colors: ['#f48fb1'], unit: 'g',  smoothRadius: 2 },
    { label: 'G-Fuerza Longitudinal',  keys: ['g_long'], colors: ['#80cbc4'], unit: 'g',  smoothRadius: 2 },
    { label: 'G-Fuerza Vertical',      keys: ['g_vert'], colors: ['#fff176'], unit: 'g',  smoothRadius: 2 },
  ],
  'Frenos': [
    { label: 'Temp. Freno',  keys: ['brake_t_fl', 'brake_t_fr', 'brake_t_rl', 'brake_t_rr'], colors: CORNER_COLORS, seriesLabels: CORNER_LABELS, unit: '°C', smoothRadius: 2 },
    { label: 'Sesgo Freno',  keys: ['brake_bias'], colors: ['#ef5350'], unit: '%', smoothRadius: 2 },
  ],
  'Motor': [
    { label: 'Temp. Aceite',       keys: ['oil_temp'],   colors: ['#ffb74d'], unit: '°C', smoothRadius: 3 },
    { label: 'Temp. Agua',         keys: ['water_temp'], colors: ['#4fc3f7'], unit: '°C', smoothRadius: 3 },
    { label: 'Combustible',        keys: ['fuel_level'], colors: ['#81c784'], unit: 'L',  smoothRadius: 2 },
    { label: 'Embrague',           keys: ['clutch'],     colors: ['#ce93d8'], unit: '%',  smoothRadius: 1 },
  ],
  'Dirección': [
    { label: 'Ángulo Volante',    keys: ['steer'],        colors: ['#f48fb1'], unit: '°',  smoothRadius: 2 },
    { label: 'Par Columna Dir.', keys: ['steer_torque'], colors: ['#80cbc4'], unit: 'Nm', smoothRadius: 2 },
  ],
};

function formatLapTime(seconds: number): string {
  if (seconds <= 0) return '--';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(3).padStart(6, '0')}`;
}

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

function formatPedalPercent(value: number): string {
  const pct = normalizePedalPercent(value);
  return `${pct.toLocaleString('es-ES', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}%`;
}

export default function TelemetryScreen() {
  const { analysisResult } = useAppStore();
  const [cursorPosition, setCursorPosition] = useState<GPSPoint | null>(null);
  const [cursorSample, setCursorSample] = useState<TelemetrySample | null>(null);
  const [selectedLap, setSelectedLap] = useState<number | null>(null);
  const [chartTab, setChartTab] = useState<ChartTab>('Conducción');
  const { width: windowWidth, height: windowHeight } = useWindowDimensions();
  const isWide = windowWidth >= 900;
  const topPanelAsColumns = windowWidth >= 1100;

  const telemetrySeries = Array.isArray(analysisResult?.telemetry_series)
    ? analysisResult.telemetry_series
    : [];
  const hasTelemetry = telemetrySeries.length > 0;
  const stats = analysisResult?.session_stats ?? null;
  const lapsData = Array.isArray(analysisResult?.laps_data) ? analysisResult.laps_data : null;
  const statsLaps = Array.isArray(stats?.laps) ? stats.laps : [];
  const laps = lapsData ?? statsLaps;
  const bestLapTime = stats?.best_lap_time ?? 0;

  const availableLaps = useMemo(() => {
    const fromSeries = telemetrySeries
      .map((s) => s.lap)
      .filter((lap) => Number.isFinite(lap) && lap > 0);
    const fromStats = laps.map((l) => l.lap).filter((lap) => Number.isFinite(lap) && lap > 0);
    return Array.from(new Set([...fromSeries, ...fromStats])).sort((a, b) => a - b);
  }, [telemetrySeries, laps]);

  useEffect(() => {
    if (availableLaps.length === 0) {
      setSelectedLap(null);
      return;
    }
    if (selectedLap == null || !availableLaps.includes(selectedLap)) {
      setSelectedLap(availableLaps[0]);
    }
  }, [availableLaps, selectedLap]);

  const selectedLapSamples = useMemo(() => {
    if (selectedLap == null) return telemetrySeries;
    return telemetrySeries.filter((s) => s.lap === selectedLap);
  }, [telemetrySeries, selectedLap]);

  const selectedLapTimeOffset = useMemo(() => {
    if (selectedLapSamples.length === 0) return 0;
    return selectedLapSamples.reduce(
      (min, sample) => (sample.t < min ? sample.t : min),
      selectedLapSamples[0].t,
    );
  }, [selectedLapSamples]);

  // Max/min throttle and brake per lap — same artifact filter as TelemetryCharts.
  const lapPedalStats = useMemo(() => {
    // Must match constants in TelemetryCharts.tsx
    const ACTIVE_THR = 5, ACTIVE_BRK = 5, MIN_SAMPLES = 60;

    function filterArtifacts(values: number[], threshold: number): number[] {
      const out = [...values];
      let i = 0;
      while (i < out.length) {
        if (out[i] <= threshold) { i++; continue; }
        const start = i;
        while (i < out.length && out[i] > threshold) i++;
        const end = i - 1;
        if (end - start + 1 < MIN_SAMPLES) {
          for (let j = start; j <= end; j++) out[j] = 0;
        }
      }
      return out;
    }

    // Group normalized samples by lap.
    const groups = new Map<number, { thr: number[]; brk: number[] }>();
    for (const s of telemetrySeries) {
      if (!Number.isFinite(s.lap) || s.lap <= 0) continue;
      const thr = Math.abs(s.thr) <= 1 ? s.thr * 100 : s.thr;
      const brk = Math.abs(s.brk) <= 1 ? s.brk * 100 : s.brk;
      const g = groups.get(s.lap);
      if (!g) { groups.set(s.lap, { thr: [thr], brk: [brk] }); }
      else { g.thr.push(thr); g.brk.push(brk); }
    }

    // Filter artifacts then compute max/min per lap.
    const result = new Map<number, { maxThr: number; minThr: number; maxBrk: number; minBrk: number }>();
    for (const [lap, { thr, brk }] of groups) {
      const ft = filterArtifacts(thr, ACTIVE_THR);
      const fb = filterArtifacts(brk, ACTIVE_BRK);
      let maxThr = 0, minThr = Infinity, maxBrk = 0, minBrk = Infinity;
      for (const v of ft) { if (v > maxThr) maxThr = v; if (v < minThr) minThr = v; }
      for (const v of fb) { if (v > maxBrk) maxBrk = v; if (v < minBrk) minBrk = v; }
      result.set(lap, {
        maxThr, minThr: minThr === Infinity ? 0 : minThr,
        maxBrk, minBrk: minBrk === Infinity ? 0 : minBrk,
      });
    }
    return result;
  }, [telemetrySeries]);

  useEffect(() => {
    if (selectedLapSamples.length > 0) {
      setCursorSample(selectedLapSamples[0]);
      setCursorPosition({ lat: selectedLapSamples[0].lat, lon: selectedLapSamples[0].lon });
    } else {
      setCursorSample(null);
      setCursorPosition(null);
    }
  }, [selectedLapSamples]);

  const selectedLapGpsPoints = useMemo(
    () =>
      selectedLapSamples
        .filter(
          (s) =>
            Number.isFinite(s.lat) &&
            Number.isFinite(s.lon) &&
            s.lat >= -90 &&
            s.lat <= 90 &&
            s.lon >= -180 &&
            s.lon <= 180 &&
            (s.lat !== 0 || s.lon !== 0),
        )
        .map((s) => ({ lat: s.lat, lon: s.lon })),
    [selectedLapSamples],
  );

  const allTelemetryGpsPoints = useMemo(
    () =>
      telemetrySeries
        .filter(
          (s) =>
            Number.isFinite(s.lat) &&
            Number.isFinite(s.lon) &&
            s.lat >= -90 &&
            s.lat <= 90 &&
            s.lon >= -180 &&
            s.lon <= 180 &&
            (s.lat !== 0 || s.lon !== 0),
        )
        .map((s) => ({ lat: s.lat, lon: s.lon })),
    [telemetrySeries],
  );

  const mapPoints = selectedLapGpsPoints.length >= 2
    ? selectedLapGpsPoints
    : Array.isArray(analysisResult?.circuit_data) && analysisResult.circuit_data.length >= 2
    ? analysisResult.circuit_data
    : allTelemetryGpsPoints.length >= 2
    ? allTelemetryGpsPoints
    : [];

  const hasCircuit = mapPoints.length >= 2;

  const bestLapNumber = useMemo(() => {
    const sorted = [...laps]
      .filter((l) => Number.isFinite(l.duration) && l.duration > 0)
      .sort((a, b) => a.duration - b.duration);
    return sorted.length > 0 ? sorted[0].lap : null;
  }, [laps]);

  const lapSelectorVisible = hasTelemetry && availableLaps.length > 0;
  const targetTopPanelHeight = Math.max(Math.floor(windowHeight * 0.4), 220);
  const topPanelHeight = Math.min(targetTopPanelHeight, 380);
  const mapWidth = topPanelAsColumns
    ? Math.max(Math.min(windowWidth * 0.52, 920), 540)
    : Math.max(windowWidth - 48, 320);
  const mapHeight = topPanelAsColumns
    ? Math.max(Math.min(topPanelHeight - 56, 320), 240)
    : isWide
    ? 280
    : 220;

  const handleCursorIndex = useCallback((_: number, sample: TelemetrySample) => {
    if (sample.lat !== 0 || sample.lon !== 0) {
      setCursorPosition({ lat: sample.lat, lon: sample.lon });
    }
    setCursorSample(sample);
  }, []);

  if (!analysisResult) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.center}>
        <Text style={styles.emptyText}>Sube archivos en Upload para ver la telemetria</Text>
      </ScrollView>
    );
  }

  if (!hasTelemetry && !hasCircuit) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.center}>
        <Text style={styles.emptyText}>Sin datos de telemetria disponibles</Text>
      </ScrollView>
    );
  }

  return (
    <View style={styles.container}>
      {/* Fixed top panel: left stats + center map + right lap selector */}
      <View style={styles.fixedPanel}>
        <View style={[styles.fixedGrid, topPanelAsColumns ? styles.fixedGridRow : styles.fixedGridColumn]}>
          <View style={[styles.fixedInfoColumn, topPanelAsColumns ? styles.fixedInfoColumnDesktop : null]}>
            <Text style={styles.sectionTitle}>Resumen</Text>
            <View style={styles.infoCard}>
              <Text style={styles.infoLabel}>Circuito</Text>
              <Text style={styles.infoValue} numberOfLines={2}>
                {stats?.circuit_name || 'Desconocido'}
              </Text>
            </View>
            <View style={styles.infoCard}>
              <Text style={styles.infoLabel}>Vueltas</Text>
              <Text style={styles.infoValue}>{stats?.total_laps ?? 0}</Text>
            </View>
            <View style={styles.infoCard}>
              <Text style={styles.infoLabel}>Mejor vuelta</Text>
              <Text style={[styles.infoValue, styles.infoValueAccent]}>
                {formatLapTime(stats?.best_lap_time ?? 0)}
              </Text>
            </View>
            <View style={styles.infoCard}>
              <Text style={styles.infoLabel}>Media</Text>
              <Text style={styles.infoValue}>{formatLapTime(stats?.avg_lap_time ?? 0)}</Text>
            </View>
          </View>

          <View style={styles.fixedMapColumn}>
            {hasCircuit && (
              <View style={styles.mapSection}>
                <Text style={styles.sectionTitle}>Mapa del Circuito</Text>
                <CircuitMap
                  gpsPoints={mapPoints}
                  issues={analysisResult.issues_on_map}
                  currentPosition={cursorPosition}
                  width={mapWidth}
                  height={mapHeight}
                />
              </View>
            )}
            {!hasCircuit && (
              <View style={styles.noCircuitBadge}>
                <Text style={styles.noCircuitText}>Sin datos GPS para trazar el circuito</Text>
              </View>
            )}
          </View>

          <View
            style={[
              styles.fixedLapsColumn,
              topPanelAsColumns ? styles.fixedLapsColumnDesktop : null,
              topPanelAsColumns ? { maxHeight: mapHeight + 34 } : null,
            ]}
          >
            <Text style={styles.sectionTitle}>Selector de Vuelta</Text>
            <View style={styles.lapSelectorPanel}>
              <ScrollView
                style={styles.lapSelectorScroll}
                contentContainerStyle={styles.lapSelectorList}
                nestedScrollEnabled
                showsVerticalScrollIndicator={false}
              >
                {lapSelectorVisible ? (
                  availableLaps.map((lap) => {
                    const isActive = lap === selectedLap;
                    const isBest = bestLapNumber != null && lap === bestLapNumber;
                    return (
                      <Pressable
                        key={lap}
                        style={[
                          styles.lapRow,
                          isBest ? styles.lapRowBest : null,
                          isActive ? styles.lapRowActive : null,
                        ]}
                        onPress={() => setSelectedLap(lap)}
                      >
                        <Text style={[styles.lapRowText, isActive ? styles.lapRowTextActive : null]}>
                          Vuelta {lap}
                        </Text>
                        {isBest ? (
                          <Text style={[styles.lapRowBadge, isActive ? styles.lapRowBadgeActive : null]}>★ Mejor</Text>
                        ) : null}
                      </Pressable>
                    );
                  })
                ) : (
                  <Text style={styles.noLapsText}>Sin vueltas disponibles</Text>
                )}
              </ScrollView>
            </View>
          </View>
        </View>

        {cursorSample && (
          <View style={styles.fixedCursorBar}>
            <Text style={styles.fixedCursorBarText}>
              t = {formatCursorTimestamp(Math.max(0, cursorSample.t - selectedLapTimeOffset))} {' | '} Vuelta{' '}
              <Text style={styles.fixedCursorBarHighlight}>{cursorSample.lap}</Text>
              {' | '}
              <Text style={styles.fixedCursorSpeed}>{cursorSample.spd.toFixed(0)} km/h</Text>
              {'  '}
              <Text style={styles.fixedCursorThrottle}>{formatPedalPercent(cursorSample.thr)}</Text>
              {' '}
              <Text style={styles.fixedCursorBrake}>{formatPedalPercent(cursorSample.brk)}</Text>
              {'  '}
              <Text style={styles.fixedCursorRpm}>{cursorSample.rpm.toFixed(0)} rpm</Text>
              {'  '}
              <Text style={styles.fixedCursorGear}>{Math.round(cursorSample.gear)}ª</Text>
            </Text>
          </View>
        )}
      </View>

      {/* Scrollable body: charts + lap table */}
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
      >
        {hasTelemetry && (
          <View style={styles.chartsSection}>
            <Text style={styles.sectionTitle}>Telemetria</Text>
            {/* Sub-tab bar */}
            <View style={styles.chartTabBar}>
              {CHART_TABS.map((tab) => (
                <Pressable
                  key={tab}
                  style={[styles.chartTabItem, chartTab === tab && styles.chartTabItemActive]}
                  onPress={() => setChartTab(tab)}
                >
                  <Text style={[styles.chartTabLabel, chartTab === tab && styles.chartTabLabelActive]}>
                    {tab}
                  </Text>
                </Pressable>
              ))}
            </View>
            <TelemetryCharts
              samples={selectedLapSamples}
              onIndexChange={handleCursorIndex}
              showCursorBar={false}
              charts={TAB_CHARTS[chartTab]}
            />
          </View>
        )}

        {/* Lap table */}
        {laps.length > 0 && (
          <View style={styles.tableSection}>
            <Text style={styles.sectionTitle}>Vueltas</Text>
            {/* Header */}
            <View style={[styles.tableRow, styles.tableHeader]}>
              <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.6 }]}>#</Text>
              <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 1.2 }]}>Tiempo</Text>
              <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 1 }]}>Avg km/h</Text>
              <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 1 }]}>Max km/h</Text>
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.9 }]}>Aceler.</Text>}
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.85, color: '#66bb6a' }]}>Acel.↑</Text>}
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.85, color: '#66bb6a' }]}>Acel.↓</Text>}
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.9 }]}>Freno</Text>}
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.85, color: '#ef5350' }]}>Freno↑</Text>}
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.85, color: '#ef5350' }]}>Freno↓</Text>}
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 1 }]}>RPM avg</Text>}
            </View>
            {[...laps]
              .sort((a, b) => a.lap - b.lap)
              .map((lap, idx) => {
                const isBest = Math.abs(lap.duration - bestLapTime) < 0.001 && bestLapTime > 0;
                return (
                  <View
                    key={idx}
                    style={[styles.tableRow, isBest ? styles.tableRowBest : idx % 2 === 0 ? styles.tableRowEven : null]}
                  >
                    <Text style={[styles.tableCell, { flex: 0.6, color: isBest ? '#4caf50' : '#888' }]}>
                      {isBest ? '★ ' : ''}{lap.lap}
                    </Text>
                    <Text style={[styles.tableCell, { flex: 1.2, color: isBest ? '#4caf50' : '#fff', fontWeight: isBest ? '700' : '400' }]}>
                      {formatLapTime(lap.duration)}
                    </Text>
                    <Text style={[styles.tableCell, { flex: 1 }]}>{lap.avg_speed.toFixed(1)}</Text>
                    <Text style={[styles.tableCell, { flex: 1 }]}>{lap.max_speed.toFixed(1)}</Text>
                    {isWide && (
                      <Text style={[styles.tableCell, { flex: 0.9, color: '#66bb6a' }]}>
                        {lap.avg_throttle != null ? formatPedalPercent(lap.avg_throttle) : '—'}
                      </Text>
                    )}
                    {isWide && (() => {
                      const ps = lapPedalStats.get(lap.lap);
                      return (
                        <>
                          <Text style={[styles.tableCell, { flex: 0.85, color: '#66bb6a' }]}>
                            {ps != null ? `${ps.maxThr.toFixed(0)}%` : '—'}
                          </Text>
                          <Text style={[styles.tableCell, { flex: 0.85, color: '#66bb6a' }]}>
                            {ps != null ? `${ps.minThr.toFixed(0)}%` : '—'}
                          </Text>
                        </>
                      );
                    })()}
                    {isWide && (
                      <Text style={[styles.tableCell, { flex: 0.9, color: '#ef5350' }]}>
                        {lap.avg_brake != null ? formatPedalPercent(lap.avg_brake) : '—'}
                      </Text>
                    )}
                    {isWide && (() => {
                      const ps = lapPedalStats.get(lap.lap);
                      return (
                        <>
                          <Text style={[styles.tableCell, { flex: 0.85, color: '#ef5350' }]}>
                            {ps != null ? `${ps.maxBrk.toFixed(0)}%` : '—'}
                          </Text>
                          <Text style={[styles.tableCell, { flex: 0.85, color: '#ef5350' }]}>
                            {ps != null ? `${ps.minBrk.toFixed(0)}%` : '—'}
                          </Text>
                        </>
                      );
                    })()}
                    {isWide && (
                      <Text style={[styles.tableCell, { flex: 1, color: '#ffa726' }]}>
                        {lap.avg_rpm != null ? `${Math.round(lap.avg_rpm)}` : '—'}
                      </Text>
                    )}
                  </View>
                );
              })}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#090919',
  },
  scrollView: {
    flex: 1,
  },
  fixedPanel: {
    backgroundColor: '#090919',
    borderBottomWidth: 1,
    borderBottomColor: '#1e1e3a',
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
  },
  fixedCursorBar: {
    marginTop: 8,
    backgroundColor: '#111128',
    borderWidth: 1,
    borderColor: '#1e1e3a',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 7,
  },
  fixedCursorBarText: {
    color: '#aaa',
    fontSize: 13,
    fontFamily: 'monospace',
  },
  fixedCursorBarHighlight: {
    color: '#fff',
    fontWeight: '700',
  },
  fixedCursorSpeed: {
    color: '#4fc3f7',
  },
  fixedCursorThrottle: {
    color: '#66bb6a',
  },
  fixedCursorBrake: {
    color: '#ef5350',
  },
  fixedCursorRpm: {
    color: '#ffa726',
  },
  fixedCursorGear: {
    color: '#ce93d8',
  },
  fixedGrid: {
    gap: 14,
  },
  fixedGridRow: {
    flexDirection: 'row',
    alignItems: 'stretch',
  },
  fixedGridColumn: {
    flexDirection: 'column',
  },
  fixedInfoColumn: {
    gap: 8,
  },
  fixedInfoColumnDesktop: {
    width: 220,
  },
  fixedMapColumn: {
    flex: 1,
  },
  fixedLapsColumn: {
    minHeight: 100,
  },
  fixedLapsColumnDesktop: {
    width: 250,
  },
  content: {
    padding: 16,
    paddingBottom: 40,
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  emptyText: {
    color: '#555',
    fontSize: 14,
    fontStyle: 'italic',
    textAlign: 'center',
  },
  infoCard: {
    backgroundColor: '#111128',
    borderRadius: 8,
    padding: 10,
    borderWidth: 1,
    borderColor: '#1e1e3a',
  },
  infoLabel: {
    color: '#555',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    marginBottom: 4,
  },
  infoValue: {
    color: '#ddd',
    fontSize: 16,
    fontWeight: '700',
    fontFamily: 'monospace',
  },
  infoValueAccent: {
    color: '#4caf50',
  },
  // â”€â”€ Section titles â”€â”€
  sectionTitle: {
    color: '#666',
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.5,
    textTransform: 'uppercase',
    marginBottom: 10,
    marginTop: 4,
  },
  // â”€â”€ Map â”€â”€
  mapSection: {
    marginBottom: 8,
  },
  noCircuitBadge: {
    backgroundColor: '#111120',
    borderRadius: 6,
    padding: 12,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#222240',
    alignItems: 'center',
  },
  noCircuitText: {
    color: '#444',
    fontSize: 12,
    fontStyle: 'italic',
  },
  // â”€â”€ Charts â”€â”€
  chartsSection: {
    marginBottom: 20,
    marginHorizontal: -16, // bleed to edges
  },
  lapSelectorPanel: {
    paddingTop: 8,
    paddingBottom: 4,
    backgroundColor: '#111120',
    borderWidth: 1,
    borderColor: '#222240',
    borderRadius: 8,
    paddingHorizontal: 10,
  },
  lapSelectorScroll: {
    maxHeight: 250,
  },
  lapSelectorList: {
    gap: 8,
    paddingBottom: 8,
  },
  lapRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 34,
    borderWidth: 1,
    borderColor: '#2a2a48',
    backgroundColor: '#101026',
    borderRadius: 8,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  lapRowBest: {
    borderColor: '#4caf50',
  },
  lapRowActive: {
    backgroundColor: '#66bb6a',
    borderColor: '#66bb6a',
  },
  lapRowText: {
    color: '#b2b7d6',
    fontSize: 12,
    fontWeight: '600',
  },
  lapRowTextActive: {
    color: '#0b1b0b',
  },
  lapRowBadge: {
    color: '#8edc92',
    fontSize: 11,
    fontWeight: '700',
  },
  lapRowBadgeActive: {
    color: '#123b12',
  },
  noLapsText: {
    color: '#666',
    fontSize: 12,
    fontStyle: 'italic',
  },
  // â”€â”€ Lap table â”€â”€
  tableSection: {
    marginBottom: 24,
  },
  tableRow: {
    flexDirection: 'row',
    paddingVertical: 7,
    paddingHorizontal: 10,
    borderRadius: 4,
    alignItems: 'center',
  },
  tableHeader: {
    backgroundColor: '#111128',
    marginBottom: 4,
    borderRadius: 6,
  },
  tableRowEven: {
    backgroundColor: '#0d0d20',
  },
  tableRowBest: {
    backgroundColor: '#071507',
    borderWidth: 1,
    borderColor: '#2e6c2e',
  },
  tableCell: {
    color: '#bbb',
    fontSize: 13,
    fontFamily: 'monospace',
    textAlign: 'right',
    paddingHorizontal: 4,
  },
  tableCellHdr: {
    color: '#555',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.8,
    textTransform: 'uppercase',
  },
  // ── Chart sub-tab bar ──
  chartTabBar: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    paddingHorizontal: 16,
    paddingBottom: 10,
    paddingTop: 2,
  },
  chartTabItem: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    backgroundColor: '#111128',
    borderWidth: 1,
    borderColor: '#2a2a48',
  },
  chartTabItemActive: {
    backgroundColor: '#1a3a6a',
    borderColor: '#4fc3f7',
  },
  chartTabLabel: {
    color: '#666',
    fontSize: 12,
    fontWeight: '600',
  },
  chartTabLabelActive: {
    color: '#4fc3f7',
  },
});
