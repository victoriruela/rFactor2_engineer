import { useCallback, useState } from 'react';
import { View, Text, StyleSheet, ScrollView } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import type { GPSPoint, TelemetrySample } from '../../src/api';
import CircuitMap from '../../src/components/CircuitMap';
import TelemetryCharts from '../../src/components/TelemetryCharts';

export default function TelemetryScreen() {
  const { analysisResult } = useAppStore();
  const [cursorPosition, setCursorPosition] = useState<GPSPoint | null>(null);

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
        <Text style={styles.emptyText}>Carga un análisis primero en la pestaña "Análisis AI"</Text>
      </ScrollView>
    );
  }

  const hasTelemetry = analysisResult.telemetry_series && analysisResult.telemetry_series.length > 0;
  const hasCircuit = analysisResult.circuit_data && analysisResult.circuit_data.length > 0;

  if (!hasTelemetry && !hasCircuit) {
    return (
      <ScrollView style={styles.container} contentContainerStyle={styles.center}>
        <Text style={styles.emptyText}>Sin datos de telemetría disponibles</Text>
      </ScrollView>
    );
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>Telemetría</Text>

      {/* Telemetry charts */}
      {hasTelemetry && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Gráficos de Telemetría</Text>
          <TelemetryCharts
            samples={analysisResult.telemetry_series}
            onIndexChange={handleCursorIndex}
          />
        </View>
      )}

      {/* Circuit map with synchronized cursor */}
      {hasCircuit && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Circuito</Text>
          <CircuitMap
            gpsPoints={analysisResult.circuit_data}
            issues={analysisResult.issues_on_map}
            currentPosition={cursorPosition}
          />
        </View>
      )}

      {/* Telemetry stats */}
      {hasTelemetry && analysisResult.session_stats && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Estadísticas de la Sesión</Text>
          <View style={styles.statsGrid}>
            <View style={styles.statItem}>
              <Text style={styles.statLabel}>Total de Vueltas</Text>
              <Text style={styles.statValue}>{analysisResult.session_stats.total_laps}</Text>
            </View>
            <View style={styles.statItem}>
              <Text style={styles.statLabel}>Mejor Vuelta</Text>
              <Text style={styles.statValue}>
                {analysisResult.session_stats.best_lap_time.toFixed(3)}s
              </Text>
            </View>
            <View style={styles.statItem}>
              <Text style={styles.statLabel}>Vuelta Media</Text>
              <Text style={styles.statValue}>
                {analysisResult.session_stats.avg_lap_time.toFixed(3)}s
              </Text>
            </View>
          </View>

          {/* Detailed lap data */}
          {analysisResult.laps_data && analysisResult.laps_data.length > 0 && (
            <View style={styles.lapsSection}>
              <Text style={styles.subsectionTitle}>Detalles por Vuelta</Text>
              {analysisResult.laps_data.map((lap, idx) => (
                <View
                  key={idx}
                  style={[
                    styles.lapRow,
                    lap.duration === analysisResult.session_stats?.best_lap_time &&
                      styles.lapRowBest,
                  ]}
                >
                  <Text style={styles.lapNumber}>Vuelta {lap.lap}</Text>
                  <View style={styles.lapStats}>
                    <Text style={styles.lapStat}>{lap.duration.toFixed(3)}s</Text>
                    <Text style={styles.lapStat}>{lap.avg_speed.toFixed(1)} km/h</Text>
                    <Text style={styles.lapStat}>Max: {lap.max_speed.toFixed(1)} km/h</Text>
                  </View>
                </View>
              ))}
            </View>
          )}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  content: {
    padding: 24,
    alignItems: 'center',
  },
  center: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyText: {
    color: '#666',
    fontSize: 14,
    fontStyle: 'italic',
    textAlign: 'center',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 24,
  },
  section: {
    width: '100%',
    maxWidth: 800,
    marginBottom: 24,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
    paddingBottom: 6,
  },
  subsectionTitle: {
    fontSize: 14,
    fontWeight: '600',
    color: '#e53935',
    marginTop: 12,
    marginBottom: 8,
    textTransform: 'uppercase',
  },
  statsGrid: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 12,
    marginBottom: 16,
    flexWrap: 'wrap',
  },
  statItem: {
    flex: 1,
    minWidth: 120,
    backgroundColor: '#0d0d1f',
    borderRadius: 6,
    padding: 12,
    borderLeftWidth: 3,
    borderLeftColor: '#e53935',
    alignItems: 'center',
  },
  statLabel: {
    color: '#888',
    fontSize: 11,
    fontWeight: '600',
    marginBottom: 4,
    textTransform: 'uppercase',
  },
  statValue: {
    color: '#e53935',
    fontSize: 18,
    fontWeight: 'bold',
  },
  lapsSection: {
    marginTop: 12,
  },
  lapRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 8,
    paddingHorizontal: 10,
    marginVertical: 2,
    backgroundColor: '#0d0d1f',
    borderRadius: 4,
    borderLeftWidth: 2,
    borderLeftColor: '#444',
  },
  lapRowBest: {
    borderLeftColor: '#4caf50',
    backgroundColor: '#0a0f1f',
  },
  lapNumber: {
    color: '#ccc',
    fontWeight: '600',
    minWidth: 80,
  },
  lapStats: {
    flexDirection: 'row',
    gap: 12,
    flex: 1,
    justifyContent: 'flex-end',
  },
  lapStat: {
    color: '#aaa',
    fontSize: 12,
    minWidth: 60,
    textAlign: 'right',
  },
});
