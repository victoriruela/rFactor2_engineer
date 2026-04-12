import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, useWindowDimensions, Pressable, Platform } from 'react-native';
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
    { label: 'Desgaste Neumático', keys: ['tyre_w_fl', 'tyre_w_fr', 'tyre_w_rl', 'tyre_w_rr'],       colors: CORNER_COLORS, seriesLabels: CORNER_LABELS, unit: '%',    smoothRadius: 2 },
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
  const minutes = Math.floor(seconds / 60);
  const secondsPart = seconds - minutes * 60;
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

function filterDisplayLaps<T extends { lap: number; duration: number; lap_distance?: number }>(laps: T[]): T[] {
  const sorted = laps
    .filter((lap) => Number.isFinite(lap.lap) && lap.lap >= 0 && Number.isFinite(lap.duration) && lap.duration > 0)
    .sort((a, b) => a.lap - b.lap);

  if (sorted.length === 0) return sorted;

  // Remove lap 0 (formation/outlap) if present — race sessions in rFactor2 start with a
  // formation lap recorded as lap 0. Practice sessions don't have it, so we keep from [0].
  const withoutFormation = sorted[0].lap === 0 ? sorted.slice(1) : sorted;

  // Remove the last entry (inlap / incomplete lap).
  return withoutFormation.length > 1 ? withoutFormation.slice(0, -1) : withoutFormation;
}

export default function TelemetryScreen() {
  const { analysisResult } = useAppStore();
  const [cursorPosition, setCursorPosition] = useState<GPSPoint | null>(null);
  const [cursorSample, setCursorSample] = useState<TelemetrySample | null>(null);
  const [selectedLap, setSelectedLap] = useState<number | null>(null);
  const [chartTab, setChartTab] = useState<ChartTab>('Conducción');
  const [panelHeight, setPanelHeight] = useState<number | null>(null);
  const dragRef = useRef<{ startY: number; startH: number } | null>(null);
  const panelHeightRef = useRef<number | null>(null);
  panelHeightRef.current = panelHeight;
  const fixedPanelRef = useRef<View>(null);
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
  // laps_data is already filtered by preparsedClientPayload; only apply
  // filterDisplayLaps when falling back to the raw stats.laps array.
  const laps = useMemo(
    () => (lapsData ? lapsData : filterDisplayLaps(statsLaps)),
    [lapsData, statsLaps],
  );
  const bestLapTime = useMemo(() => {
    const lapDurations = laps.map((lap) => lap.duration).filter((duration) => duration > 0);
    return lapDurations.length > 0 ? Math.min(...lapDurations) : 0;
  }, [laps]);
  const avgLapTime = useMemo(() => {
    const lapDurations = laps.map((lap) => lap.duration).filter((duration) => duration > 0);
    return lapDurations.length > 0
      ? lapDurations.reduce((sum, duration) => sum + duration, 0) / lapDurations.length
      : 0;
  }, [laps]);

  /** Average tyre wear per lap (percentage points per lap, per corner). */
  const avgWearPerLap = useMemo(() => {
    const keys = ['wear_fl', 'wear_fr', 'wear_rl', 'wear_rr'] as const;
    const sums = [0, 0, 0, 0];
    let count = 0;
    for (const lap of laps) {
      const vals = keys.map((k) => lap[k]);
      if (vals.every((v) => v != null && Number.isFinite(v))) {
        vals.forEach((v, i) => { sums[i] += v!; });
        count += 1;
      }
    }
    if (count === 0) return null;
    return sums.map((s) => s / count) as [number, number, number, number];
  }, [laps]);

  /** Average fuel consumed per lap (litres). */
  const avgFuelPerLap = useMemo(() => {
    const vals = laps.map((l) => l.fuel_used).filter((v): v is number => v != null && Number.isFinite(v) && v > 0);
    if (vals.length === 0) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  }, [laps]);
  const circuitName = stats?.circuit_name && stats.circuit_name.trim().length > 0 && stats.circuit_name.trim().toLowerCase() !== 'desconocido'
    ? stats.circuit_name
    : 'Desconocido';

  const availableLaps = useMemo(() => {
    return laps.map((lap) => lap.lap).filter((lap) => Number.isFinite(lap) && lap > 0);
  }, [laps]);

  const lapDurationByNumber = useMemo(() => {
    return new Map(laps.map((lap) => [lap.lap, lap.duration]));
  }, [laps]);

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

  /** GPS-precise lap duration from laps_data (or time-span fallback). */
  const selectedLapPreciseDuration = useMemo(() => {
    if (selectedLap == null) return 0;
    const lapData = laps.find((l) => l.lap === selectedLap);
    return lapData?.duration ?? 0;
  }, [laps, selectedLap]);

  /** Raw sample time span (t_last − t_first). */
  const selectedLapSampleSpan = useMemo(() => {
    if (selectedLapSamples.length < 2) return 0;
    return selectedLapSamples[selectedLapSamples.length - 1].t - selectedLapSamples[0].t;
  }, [selectedLapSamples]);

  // Peak throttle/brake come from the backend LapStats (computed at full resolution
  // before downsampling), so no separate frontend computation is needed.

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

  const mapPoints = selectedLap == null
    ? selectedLapGpsPoints
    : selectedLapGpsPoints.length >= 2
    ? selectedLapGpsPoints
    : [];

  const hasCircuit = mapPoints.length >= 2;

  const bestLapNumber = useMemo(() => {
    const sorted = [...laps]
      .filter((l) => Number.isFinite(l.duration) && l.duration > 0)
      .sort((a, b) => a.duration - b.duration);
    return sorted.length > 0 ? sorted[0].lap : null;
  }, [laps]);

  const lapSelectorVisible = hasTelemetry && availableLaps.length > 0;
  const defaultTopPanelHeight = Math.min(Math.max(Math.floor(windowHeight * 0.4), 220), 380);
  const topPanelHeight = panelHeight ?? defaultTopPanelHeight;
  const mapWidth = topPanelAsColumns
    ? Math.max(
        320,
        windowWidth
          - 32 // fixedPanel horizontal padding (16 + 16)
          - 28 // fixedGrid gaps between 3 columns (14 + 14)
          - 220 // fixedInfoColumnDesktop width
          - 250, // fixedLapsColumnDesktop width
      )
    : Math.max(windowWidth - 48, 320);
  const mapHeight = topPanelAsColumns
    ? Math.max(Math.min(topPanelHeight - 56, 320), 240)
    : isWide
    ? 280
    : 220;
  const topColumnHeight = mapHeight + 34;

  const handleCursorIndex = useCallback((_: number, sample: TelemetrySample) => {
    if (sample.lat !== 0 || sample.lon !== 0) {
      setCursorPosition({ lat: sample.lat, lon: sample.lon });
    }
    setCursorSample(sample);
  }, []);

  // ── Resizable divider drag handlers (web only) ──
  const MIN_PANEL = 120;
  const MAX_PANEL = Math.floor(windowHeight * 0.75);

  useEffect(() => {
    if (Platform.OS !== 'web') return;
    const onMouseMove = (e: MouseEvent) => {
      const d = dragRef.current;
      if (!d) return;
      e.preventDefault();
      const newH = Math.max(MIN_PANEL, Math.min(MAX_PANEL, d.startH + (e.clientY - d.startY)));
      setPanelHeight(newH);
    };
    const onMouseUp = () => {
      if (dragRef.current) {
        dragRef.current = null;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
      }
    };
    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, [MAX_PANEL]);

  const handleDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    // Use the actual rendered height of the panel (which may be smaller than
    // the state value when maxHeight > content height) so dragging responds
    // immediately instead of requiring the user to move past the dead zone.
    let actualH = panelHeightRef.current ?? defaultTopPanelHeight;
    if (Platform.OS === 'web' && fixedPanelRef.current) {
      const el = fixedPanelRef.current as unknown as HTMLElement;
      if (el.offsetHeight) actualH = el.offsetHeight;
    }
    dragRef.current = { startY: (e as unknown as MouseEvent).clientY, startH: actualH };
    document.body.style.cursor = 'row-resize';
    document.body.style.userSelect = 'none';
  }, [defaultTopPanelHeight]);

  if (!analysisResult) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.center}>
        <Text style={styles.emptyText}>Sube archivos en Subida para ver la telemetria</Text>
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
      <View ref={fixedPanelRef} style={[styles.fixedPanel, { maxHeight: topPanelHeight }]}>
        <View style={[styles.fixedGrid, topPanelAsColumns ? styles.fixedGridRow : styles.fixedGridColumn]}>
          <View
            style={[
              styles.fixedInfoColumn,
              topPanelAsColumns ? styles.fixedInfoColumnDesktop : null,
              topPanelAsColumns ? { height: topColumnHeight, overflow: 'hidden' } : null,
            ]}
          >
            <Text style={styles.sectionTitle}>Resumen</Text>
            <ScrollView
              nestedScrollEnabled
              showsVerticalScrollIndicator={false}
              style={{ flex: 1 }}
              contentContainerStyle={{ gap: 5 }}
            >
            {avgWearPerLap && (
              <View style={styles.infoCard}>
                <Text style={styles.infoLabel}>Desgaste medio / vuelta</Text>
                <Text style={styles.infoValueSmall}>
                  FL {avgWearPerLap[0].toFixed(2)}%  FR {avgWearPerLap[1].toFixed(2)}%
                </Text>
                <Text style={styles.infoValueSmall}>
                  RL {avgWearPerLap[2].toFixed(2)}%  RR {avgWearPerLap[3].toFixed(2)}%
                </Text>
              </View>
            )}
            {avgFuelPerLap != null && (
              <View style={styles.infoCard}>
                <Text style={styles.infoLabel}>Combustible medio / vuelta</Text>
                <Text style={styles.infoValueCompact}>{avgFuelPerLap.toFixed(2)} L</Text>
              </View>
            )}
            <View style={styles.infoCard}>
              <Text style={styles.infoLabel}>Mejor vuelta</Text>
              <Text style={[styles.infoValueCompact, styles.infoValueAccent]}>
                {formatLapTime(bestLapTime)}
              </Text>
            </View>
            <View style={styles.infoCard}>
              <Text style={styles.infoLabel}>Media</Text>
              <Text style={styles.infoValueCompact}>{formatLapTime(avgLapTime)}</Text>
            </View>
            <View style={styles.infoCard}>
              <Text style={styles.infoLabel}>Vueltas</Text>
              <Text style={styles.infoValueCompact}>{laps.length}</Text>
            </View>
            </ScrollView>
          </View>

          <View style={styles.fixedMapColumn}>
            {hasCircuit && (
              <View style={styles.mapSection}>
                <Text style={styles.sectionTitle}>
                  Mapa del Circuito{circuitName !== 'Desconocido' ? ` (${circuitName})` : ''}
                </Text>
                <CircuitMap
                  gpsPoints={mapPoints}
                  telemetrySamples={selectedLapSamples}
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
              topPanelAsColumns ? { height: topColumnHeight } : null,
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
                    const lapDuration = lapDurationByNumber.get(lap) ?? 0;
                    const lapTimeText = formatLapTime(lapDuration);
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
                        <View style={styles.lapRowMain}>
                          <Text style={[styles.lapRowText, isActive ? styles.lapRowTextActive : null]}>
                            Vuelta {lap}
                          </Text>
                          {isBest ? (
                            <Text style={[styles.lapRowBadge, isActive ? styles.lapRowBadgeActive : null]}>★ Mejor</Text>
                          ) : null}
                        </View>
                        <Text style={[styles.lapRowTime, isActive ? styles.lapRowTimeActive : null]}>
                          ({lapTimeText})
                        </Text>
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

      </View>

      {/* Cursor bar — outside fixedPanel so it never gets clipped */}
      {hasTelemetry && (
        <View style={styles.fixedCursorBar}>
          <View style={styles.fixedCursorBarRow}>
            {CHART_TABS.map((tab) => (
              <Pressable
                key={tab}
                style={[styles.inlineTabItem, chartTab === tab && styles.inlineTabItemActive]}
                onPress={() => setChartTab(tab)}
              >
                <Text style={[styles.inlineTabLabel, chartTab === tab && styles.inlineTabLabelActive]}>
                  {tab}
                </Text>
              </Pressable>
            ))}
            {cursorSample && (
              <>
                <Text style={styles.fixedCursorBarText}>{' │ '}</Text>
                <Text style={styles.fixedCursorBarText}>
                  {`t = ${formatCursorTimestamp(Math.max(0,
                    selectedLapPreciseDuration > 0 && selectedLapSampleSpan > 0
                      ? (cursorSample.t - selectedLapTimeOffset) * (selectedLapPreciseDuration / selectedLapSampleSpan)
                      : cursorSample.t - selectedLapTimeOffset,
                  ))} | Vuelta `}
                </Text>
                <Text style={[styles.fixedCursorBarText, styles.fixedCursorBarHighlight]}>{cursorSample.lap}</Text>
                <Text style={styles.fixedCursorBarText}>{' | '}</Text>
                <Text style={[styles.fixedCursorBarText, styles.fixedCursorSpeed]}>{cursorSample.spd.toFixed(0)} km/h</Text>
                <Text style={[styles.fixedCursorBarText, styles.fixedCursorThrottle]}>{formatPedalPercent(cursorSample.thr)}</Text>
                <Text style={[styles.fixedCursorBarText, styles.fixedCursorBrake]}>{formatPedalPercent(cursorSample.brk)}</Text>
                <Text style={[styles.fixedCursorBarText, styles.fixedCursorRpm]}>{cursorSample.rpm.toFixed(0)} rpm</Text>
                <Text style={[styles.fixedCursorBarText, styles.fixedCursorGear]}>{Math.round(cursorSample.gear)}ª</Text>
              </>
            )}
          </View>
        </View>
      )}

      {/* Resize drag handle */}
      {Platform.OS === 'web' && (
        <View
          style={styles.resizeHandle}
          // @ts-ignore web-only mouse events
          onMouseDown={handleDividerMouseDown}
        >
          <View style={styles.resizeHandleBar} />
        </View>
      )}

      {/* Scrollable body: charts + lap table */}
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
      >
        {hasTelemetry && (
          <View style={styles.chartsSection}>
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
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.9, color: '#66bb6a' }]}>Acel.</Text>}
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.85, color: '#66bb6a' }]}>Acel.↑</Text>}
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.9 }]}>Freno</Text>}
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.85, color: '#ef5350' }]}>Freno↑</Text>}
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
                    {isWide && (
                      <Text style={[styles.tableCell, { flex: 0.85, color: '#66bb6a' }]}>
                        {lap.max_throttle != null ? `${normalizePedalPercent(lap.max_throttle).toFixed(0)}%` : '—'}
                      </Text>
                    )}
                    {isWide && (
                      <Text style={[styles.tableCell, { flex: 0.9, color: '#ef5350' }]}>
                        {lap.avg_brake != null ? formatPedalPercent(lap.avg_brake) : '—'}
                      </Text>
                    )}
                    {isWide && (
                      <Text style={[styles.tableCell, { flex: 0.85, color: '#ef5350' }]}>
                        {lap.max_brake != null ? `${normalizePedalPercent(lap.max_brake).toFixed(0)}%` : '—'}
                      </Text>
                    )}
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
    borderBottomWidth: 0,
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
    overflow: 'hidden',
  },
  resizeHandle: {
    height: 10,
    backgroundColor: '#090919',
    borderBottomWidth: 1,
    borderBottomColor: '#1e1e3a',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'row-resize',
  } as object,
  resizeHandleBar: {
    width: 48,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#333355',
  },
  fixedCursorBar: {
    backgroundColor: '#111128',
    borderWidth: 1,
    borderColor: '#1e1e3a',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 7,
    marginHorizontal: 16,
    marginTop: 4,
    marginBottom: 2,
  },
  fixedCursorBarText: {
    color: '#aaa',
    fontSize: 13,
    fontFamily: 'monospace',
  },
  fixedCursorBarRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    columnGap: 8,
    rowGap: 2,
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
  restoreErrorText: {
    color: '#d36b6b',
    fontSize: 12,
    marginTop: 10,
    textAlign: 'center',
    maxWidth: 420,
  },
  retryBtn: {
    marginTop: 14,
    backgroundColor: '#e53935',
    borderRadius: 8,
    paddingVertical: 10,
    paddingHorizontal: 14,
  },
  retryBtnText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 13,
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
  infoValueSmall: {
    color: '#ddd',
    fontSize: 12,
    fontWeight: '600',
    fontFamily: 'monospace',
    lineHeight: 16,
  },
  infoValueCompact: {
    color: '#ddd',
    fontSize: 13,
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
    width: '100%',
    alignItems: 'stretch',
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
    flex: 1,
    paddingTop: 8,
    paddingBottom: 4,
    backgroundColor: '#111120',
    borderWidth: 1,
    borderColor: '#222240',
    borderRadius: 8,
    paddingHorizontal: 10,
  },
  lapSelectorScroll: {
    flex: 1,
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
  lapRowMain: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    flexShrink: 1,
    minWidth: 0,
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
  lapRowTime: {
    color: '#e5e8ff',
    fontSize: 12,
    fontWeight: '700',
    fontFamily: 'monospace',
  },
  lapRowTimeActive: {
    color: '#0b1b0b',
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
  // ── Inline tab bar (inside cursor bar) ──
  inlineTabItem: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 14,
    backgroundColor: '#1a1a30',
    borderWidth: 1,
    borderColor: '#2a2a48',
  },
  inlineTabItemActive: {
    backgroundColor: '#1a3a6a',
    borderColor: '#4fc3f7',
  },
  inlineTabLabel: {
    color: '#555',
    fontSize: 11,
    fontWeight: '600',
  },
  inlineTabLabelActive: {
    color: '#4fc3f7',
  },
});
