import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, ScrollView, useWindowDimensions } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import type { GPSPoint } from '../../src/api';
import CircuitMap from '../../src/components/CircuitMap';
import TelemetryCharts from '../../src/components/TelemetryCharts';

function formatLapTime(seconds: number): string {
  if (seconds <= 0) return 'â€”';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(3).padStart(6, '0')}`;
}

export default function TelemetryScreen() {
  const { analysisResult } = useAppStore();
  const [cursorPosition, setCursorPosition] = useState<GPSPoint | null>(null);
  const { width: windowWidth } = useWindowDimensions();
  const isWide = windowWidth >= 900;

  const handleCursorIndex = useCallback(
    (idx: number) => {
      const series = analysisResult?.telemetry_series;
      if (!series || idx >= series.length) return;
      const sample = series[idx];
      if (sample.lat !== 0 || sample.lon !== 0) {
        setCursorPosition({ lat: sample.lat, lon: sample.lon });
      }
    },
    [analysisResult],
  );

  if (!analysisResult) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.center}>
        <Text style={styles.emptyText}>Carga un anÃ¡lisis primero en la pestaÃ±a "AnÃ¡lisis AI"</Text>
      </ScrollView>
    );
  }

  const hasTelemetry = analysisResult.telemetry_series && analysisResult.telemetry_series.length > 0;
  const hasCircuit = analysisResult.circuit_data && analysisResult.circuit_data.length > 0;
  const stats = analysisResult.session_stats;
  const laps = analysisResult.laps_data ?? stats?.laps ?? [];
  const bestLapTime = stats?.best_lap_time ?? 0;

  if (!hasTelemetry && !hasCircuit) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.center}>
        <Text style={styles.emptyText}>Sin datos de telemetrÃ­a disponibles</Text>
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      {/* â”€â”€ Session stats banner â”€â”€ */}
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

      {/* â”€â”€ Circuit map (full width, before charts) â”€â”€ */}
      {hasCircuit && (
        <View style={styles.mapSection}>
          <Text style={styles.sectionTitle}>Mapa del Circuito</Text>
          <CircuitMap
            gpsPoints={analysisResult.circuit_data}
            issues={analysisResult.issues_on_map}
            currentPosition={cursorPosition}
            width={windowWidth - 32}
            height={isWide ? 360 : 260}
          />
        </View>
      )}
      {!hasCircuit && (
        <View style={styles.noCircuitBadge}>
          <Text style={styles.noCircuitText}>Sin datos GPS para trazar el circuito</Text>
        </View>
      )}

      {/* â”€â”€ Telemetry charts â”€â”€ */}
      {hasTelemetry && (
        <View style={styles.chartsSection}>
          <Text style={styles.sectionTitle}>TelemetrÃ­a</Text>
          <TelemetryCharts
            samples={analysisResult.telemetry_series}
            onIndexChange={handleCursorIndex}
          />
        </View>
      )}

      {/* â”€â”€ Lap table â”€â”€ */}
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
                    {isBest ? 'â˜… ' : ''}{lap.lap}
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
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#090919',
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
