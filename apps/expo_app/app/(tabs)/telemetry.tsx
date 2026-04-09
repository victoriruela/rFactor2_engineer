import { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, useWindowDimensions } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import type { GPSPoint } from '../../src/api';
import CircuitMap from '../../src/components/CircuitMap';
import TelemetryCharts from '../../src/components/TelemetryCharts';

function formatLapTime(seconds: number): string {
  if (seconds <= 0) return '--';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(3).padStart(6, '0')}`;
}

export default function TelemetryScreen() {
  const { analysisResult } = useAppStore();
  const [cursorPosition, setCursorPosition] = useState<GPSPoint | null>(null);
  const [selectedLap, setSelectedLap] = useState<number | null>(null);
  const { width: windowWidth } = useWindowDimensions();
  const isWide = windowWidth >= 900;

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

  const handleCursorIndex = useCallback((_: number, sample: { lat: number; lon: number }) => {
    if (sample.lat !== 0 || sample.lon !== 0) {
      setCursorPosition({ lat: sample.lat, lon: sample.lon });
    }
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
      {/* Fixed top panel: map + lap selector — always visible */}
      <View style={styles.fixedPanel}>
        {hasCircuit && (
          <View style={styles.mapSection}>
            <Text style={styles.sectionTitle}>Mapa del Circuito</Text>
            <CircuitMap
              gpsPoints={mapPoints}
              issues={analysisResult.issues_on_map}
              currentPosition={cursorPosition}
              width={Math.max(windowWidth - 32, 320)}
              height={isWide ? 260 : 180}
            />
          </View>
        )}
        {!hasCircuit && (
          <View style={styles.noCircuitBadge}>
            <Text style={styles.noCircuitText}>Sin datos GPS para trazar el circuito</Text>
          </View>
        )}
        {lapSelectorVisible && (
          <View style={styles.lapSelectorPanel}>
            <View style={styles.lapSelectorRow}>
              {availableLaps.map((lap) => {
                const isActive = lap === selectedLap;
                const isBest = bestLapNumber != null && lap === bestLapNumber;
                return (
                  <Text
                    key={lap}
                    style={[
                      styles.lapChip,
                      isBest ? styles.lapChipBest : null,
                      isActive ? styles.lapChipActive : null,
                    ]}
                    onPress={() => setSelectedLap(lap)}
                  >
                    {isBest ? '★ ' : ''}Vuelta {lap}
                  </Text>
                );
              })}
            </View>
          </View>
        )}
      </View>

      {/* Scrollable body: stats + charts + lap table */}
      <ScrollView
        style={styles.scrollView}
        contentContainerStyle={styles.content}
      >
        {/* Session stats banner */}
        {stats && (
          <View style={styles.statsBanner}>
            <View style={styles.statCard}>
              <Text style={styles.statCardLabel}>VUELTAS</Text>
              <Text style={styles.statCardValue}>{stats.total_laps}</Text>
            </View>
            <View style={[styles.statCard, styles.statCardAccent]}>
              <Text style={styles.statCardLabel}>MEJOR VUELTA</Text>
              <Text style={[styles.statCardValue, styles.statCardValueAccent]}>
                {formatLapTime(stats.best_lap_time)}
              </Text>
            </View>
            <View style={styles.statCard}>
              <Text style={styles.statCardLabel}>MEDIA</Text>
              <Text style={styles.statCardValue}>{formatLapTime(stats.avg_lap_time)}</Text>
            </View>
            {stats.circuit_name ? (
              <View style={styles.statCard}>
                <Text style={styles.statCardLabel}>CIRCUITO</Text>
                <Text style={styles.statCardValue}>{stats.circuit_name}</Text>
              </View>
            ) : null}
          </View>
        )}

        {hasTelemetry && (
          <View style={styles.chartsSection}>
            <Text style={styles.sectionTitle}>Telemetria</Text>
            <TelemetryCharts
              samples={selectedLapSamples}
              onIndexChange={handleCursorIndex}
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
              {isWide && <Text style={[styles.tableCell, styles.tableCellHdr, { flex: 0.9 }]}>Freno</Text>}
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
                        {lap.avg_throttle != null ? `${(lap.avg_throttle * 100).toFixed(0)}%` : '—'}
                      </Text>
                    )}
                    {isWide && (
                      <Text style={[styles.tableCell, { flex: 0.9, color: '#ef5350' }]}>
                        {lap.avg_brake != null ? `${(lap.avg_brake * 100).toFixed(0)}%` : '—'}
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
    borderBottomWidth: 1,
    borderBottomColor: '#1e1e3a',
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
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
  // â”€â”€ Stats banner â”€â”€
  statsBanner: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
    marginBottom: 20,
  },
  statCard: {
    flex: 1,
    minWidth: 100,
    backgroundColor: '#111128',
    borderRadius: 8,
    padding: 14,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: '#1e1e3a',
  },
  statCardAccent: {
    borderColor: '#4caf50',
    backgroundColor: '#0a140a',
  },
  statCardLabel: {
    color: '#555',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 1,
    marginBottom: 6,
  },
  statCardValue: {
    color: '#ddd',
    fontSize: 18,
    fontWeight: '700',
    fontFamily: 'monospace',
  },
  statCardValueAccent: {
    color: '#4caf50',
    fontSize: 20,
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
    marginBottom: 20,
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
  },
  lapSelectorRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    rowGap: 8,
    columnGap: 8,
  },
  lapChip: {
    color: '#9aa0c4',
    borderWidth: 1,
    borderColor: '#2a2a48',
    backgroundColor: '#101026',
    borderRadius: 14,
    paddingHorizontal: 12,
    paddingVertical: 6,
    fontSize: 12,
    overflow: 'hidden',
  },
  lapChipBest: {
    borderColor: '#4caf50',
    color: '#8edc92',
  },
  lapChipActive: {
    color: '#0b1b0b',
    backgroundColor: '#66bb6a',
    borderColor: '#66bb6a',
    fontWeight: '700',
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
});
