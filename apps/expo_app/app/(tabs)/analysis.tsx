import { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import { analyzePreparsedStream, authUpdateConfig } from '../../src/api';
import type { ProgressEvent, SetupChange } from '../../src/api';
import SetupTable from '../../src/components/SetupTable';
import MarkdownText from '../../src/components/MarkdownText';
import ChiefReasoningFormatter from '../../src/components/ChiefReasoningFormatter';
import TelemetryExpertAnalysisFormatter from '../../src/components/TelemetryExpertAnalysisFormatter';
import { toSpanishParameterName } from '../../src/utils/labelTranslator';

const AGENT_LABELS: Record<string, string> = {
  driving: 'Análisis de conducción',
  domain_engineers: 'Ingenieros de dominio',
  suspension: 'Ing. Suspensión',
  chassis: 'Ing. Chasis',
  aero: 'Ing. Aerodinámica',
  powertrain: 'Ing. Tren motriz',
  contradictions: 'Detección de contradicciones',
  chief: 'Ingeniero jefe',
  telemetry: 'Experto de telemetría',
  specialist: 'Especialista de setup',
};

function formatLapTime(seconds: number): string {
  if (seconds <= 0) return '--';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(3).padStart(6, '0')}`;
}

export default function AnalysisScreen() {
  const {
    isAnalyzing, setAnalyzing,
    analysisResult, setAnalysisResult,
    analysisError, setAnalysisError,
    ollamaApiKey,
    lockedParameters,
    preparsedPayload,
    isUploading,
  } = useAppStore();
  const [progressMessages, setProgressMessages] = useState<ProgressEvent[]>([]);
  const [progressExpanded, setProgressExpanded] = useState(true);
  const [analysisElapsed, setAnalysisElapsed] = useState(0);

  useEffect(() => {
    if (!isAnalyzing) {
      setAnalysisElapsed(0);
      return;
    }
    const iv = setInterval(() => setAnalysisElapsed(prev => prev + 1), 1000);
    return () => clearInterval(iv);
  }, [isAnalyzing]);

  const formatElapsed = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return m > 0 ? `${m}m ${sec}s` : `${sec}s`;
  };

  const filteredSetupAnalysis = useMemo<Record<string, SetupChange[]>>(() => {
    const source = analysisResult?.setup_analysis ?? {};
    const normalize = (value?: string) => (value ?? '').trim();

    return Object.fromEntries(
      Object.entries(source)
        .map(([section, items]) => {
          const filteredItems = items.filter((item) => {
            const oldValue = normalize(item.old_value);
            const newValue = normalize(item.new_value);
            if (!newValue) {
              return false;
            }
            return newValue !== oldValue;
          });
          return [section, filteredItems];
        })
        .filter(([, items]) => items.length > 0),
    );
  }, [analysisResult?.setup_analysis]);

  const handleAnalyze = useCallback(async () => {
    if (!preparsedPayload) {
      setAnalysisError(isUploading
        ? 'Los archivos se estan procesando todavia. Espera a que termine el parseo automatico.'
        : 'Sube los archivos .ld y .svm en la pestaña "Datos" para iniciar el analisis.');
      return;
    }

    setAnalyzing(true);
    setAnalysisError(null);
    setProgressMessages([]);
    setProgressExpanded(true);

    try {
      setProgressMessages([{ type: 'progress', agent: 'driving', message: 'Analizando payload parseado en cliente...' }]);
      const apiKey = ollamaApiKey?.trim() ?? '';
      const result = await analyzePreparsedStream(
        preparsedPayload,
        '',
        'ollama_cloud',
        Array.from(lockedParameters),
        {
          model: '',
          ollamaBaseUrl: '',
          ollamaApiKey: apiKey,
        },
        (event) => {
          setProgressMessages((prev) => [...prev, event]);
        },
      );
      setAnalysisResult({
        ...result,
        circuit_data: analysisResult?.circuit_data?.length ? analysisResult.circuit_data : (result.circuit_data ?? []),
        session_stats: analysisResult?.session_stats ?? result.session_stats ?? null,
        laps_data: analysisResult?.laps_data?.length ? analysisResult.laps_data : (result.laps_data ?? []),
        telemetry_series: analysisResult?.telemetry_series?.length ? analysisResult.telemetry_series : (result.telemetry_series ?? []),
      });
      setProgressExpanded(false);

      // Auto-save API key to user profile
      authUpdateConfig(ollamaApiKey?.trim() ?? '', '').catch(() => { /* silent */ });
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error en el análisis';
      setAnalysisError(msg);
    } finally {
      setAnalyzing(false);
    }
  }, [
    preparsedPayload,
    lockedParameters,
    analysisResult,
    isUploading,
    ollamaApiKey,
    setAnalyzing,
    setAnalysisResult,
    setAnalysisError,
  ]);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>Análisis AI</Text>

      {/* Analyze button */}
      <Pressable
        style={[styles.analyzeBtn, (isAnalyzing || isUploading || (!preparsedPayload && !analysisResult)) && styles.disabled]}
        onPress={handleAnalyze}
        disabled={isAnalyzing || isUploading || (!preparsedPayload && !analysisResult)}
      >
        {isAnalyzing || isUploading ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.analyzeBtnText}>Iniciar Análisis</Text>
        )}
      </Pressable>

      {analysisError && <Text style={styles.error}>{analysisError}</Text>}

      {/* Real-time progress log - collapsible */}
      {progressMessages.length > 0 && (
        <View style={styles.section}>
          <Pressable
            style={styles.progressHeader}
            onPress={() => setProgressExpanded(!progressExpanded)}
          >
            <Text style={styles.progressHeaderText}>
              {progressExpanded ? '▼' : '▶'} Progreso del Análisis
            </Text>
          </Pressable>

          {progressExpanded && (
            <View style={styles.progressBox}>
              {progressMessages.map((ev, i) => (
                <View key={i} style={styles.progressRow}>
                  <Text style={styles.progressAgent}>
                    {AGENT_LABELS[ev.agent] ?? ev.agent}
                    {ev.section ? ` - ${ev.section}` : ''}
                  </Text>
                  <Text style={styles.progressMsg}>{ev.message}</Text>
                </View>
              ))}
              {isAnalyzing && (
                <View style={styles.progressRow}>
                  <ActivityIndicator size="small" color="#e53935" />
                  <Text style={styles.progressMsg}> Procesando... {formatElapsed(analysisElapsed)}</Text>
                </View>
              )}
            </View>
          )}
        </View>
      )}

      {/* Results */}
      {analysisResult && (
        <>
          {/* Session Stats */}
          {analysisResult.session_stats && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Estadísticas</Text>
              <View style={styles.statsBox}>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Número de Vueltas</Text>
                  <Text style={styles.statValue}>{analysisResult.session_stats.total_laps}</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Mejor Vuelta</Text>
                  <Text style={styles.statValue}>{formatLapTime(analysisResult.session_stats.best_lap_time)}</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Vuelta Media</Text>
                  <Text style={styles.statValue}>{formatLapTime(analysisResult.session_stats.avg_lap_time)}</Text>
                </View>
              </View>
            </View>
          )}

          {/* Driving Analysis - markdown rendered */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Análisis de Conducción</Text>
            <MarkdownText text={analysisResult.driving_analysis} />
          </View>

          {/* Setup Recommendations */}
          {Object.values(filteredSetupAnalysis).some((items) => items.length > 0) ? (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Recomendaciones del setup</Text>
              {lockedParameters.size > 0 && (
                <View style={styles.lockedNotice}>
                  <Text style={styles.lockedNoticeText}>
                    Parámetros fijados: {Array.from(lockedParameters).map((p) => toSpanishParameterName(p)).join(', ')}
                  </Text>
                </View>
              )}
              <SetupTable changes={filteredSetupAnalysis} />
            </View>
          ) : null}

          {/* Chief reasoning at the end */}
          {analysisResult.chief_reasoning ? (
            <View style={styles.section}>
              <ChiefReasoningFormatter reasoning={analysisResult.chief_reasoning} />
            </View>
          ) : null}

          {/* Telemetry Expert Analysis */}
          {analysisResult.telemetry_analysis ? (
            <View style={styles.section}>
              <TelemetryExpertAnalysisFormatter analysis={analysisResult.telemetry_analysis} />
            </View>
          ) : null}
        </>
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
    alignItems: 'stretch',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 24,
    textAlign: 'left',
  },
  modelRow: {
    flexDirection: 'row',
    marginBottom: 16,
    flexWrap: 'wrap',
    width: '100%',
  },
  modelHeaderRow: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: 8,
    marginBottom: 10,
  },
  modelHeaderBtns: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
  },
  modelConfigRow: {
    width: '100%',
    marginBottom: 16,
  },
  modelInput: {
    marginTop: 8,
    borderWidth: 1,
    borderColor: '#333',
    backgroundColor: '#1a1a3e',
    color: '#fff',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
  },
  label: {
    color: '#ccc',
    marginRight: 8,
    fontSize: 14,
  },
  modelList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
    width: '100%',
  },
  refreshBtn: {
    backgroundColor: '#1a1a3e',
    borderWidth: 1,
    borderColor: '#333',
    borderRadius: 8,
    paddingVertical: 8,
    paddingHorizontal: 12,
  },
  refreshBtnText: {
    color: '#ddd',
    fontSize: 12,
    fontWeight: '600',
  },
  modelError: {
    color: '#ff9800',
    fontSize: 12,
    marginBottom: 12,
  },
  modelChip: {
    paddingVertical: 6,
    paddingHorizontal: 12,
    borderRadius: 16,
    backgroundColor: '#1a1a3e',
    borderWidth: 1,
    borderColor: '#333',
  },
  modelChipActive: {
    backgroundColor: '#e53935',
    borderColor: '#e53935',
  },
  modelChipText: {
    color: '#aaa',
    fontSize: 12,
  },
  modelChipTextActive: {
    color: '#fff',
  },
  analyzeBtn: {
    backgroundColor: '#e53935',
    paddingVertical: 14,
    paddingHorizontal: 48,
    borderRadius: 8,
    marginBottom: 24,
    minWidth: 200,
    alignItems: 'center',
    alignSelf: 'flex-start',
  },
  disabled: {
    opacity: 0.5,
  },
  analyzeBtnText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 16,
  },
  error: {
    color: '#f44336',
    marginBottom: 16,
  },
  section: {
    width: '100%',
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
  statsBox: {
    flexDirection: 'row',
    justifyContent: 'space-around',
    gap: 8,
    flexWrap: 'wrap',
  },
  stat: {
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
    fontSize: 16,
    fontWeight: 'bold',
  },
  progressHeader: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    backgroundColor: '#1a1a3e',
    borderRadius: 6,
    borderLeftWidth: 3,
    borderLeftColor: '#4a90e2',
    marginBottom: 8,
  },
  progressHeaderText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  progressBox: {
    backgroundColor: '#0d0d1f',
    borderRadius: 8,
    padding: 12,
    borderWidth: 1,
    borderColor: '#222',
    gap: 8,
  },
  progressRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'flex-start',
    gap: 6,
  },
  progressAgent: {
    color: '#4a90e2',
    fontSize: 12,
    fontWeight: '600',
    minWidth: 140,
  },
  progressMsg: {
    color: '#aaa',
    fontSize: 12,
    flex: 1,
  },
  lockedNotice: {
    backgroundColor: '#ff9800',
    borderRadius: 4,
    paddingHorizontal: 10,
    paddingVertical: 6,
    marginBottom: 12,
  },
  lockedNoticeText: {
    color: '#000',
    fontSize: 12,
    fontWeight: '600',
  },
  modelSuccess: {
    color: '#4caf50',
    fontSize: 12,
    marginBottom: 12,
  },
  routingSection: {
    width: '100%',
    backgroundColor: '#1a1a3e',
    borderRadius: 8,
    padding: 12,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: '#333',
  },
  routingSectionTitle: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },
  routingFallback: {
    color: '#888',
    fontSize: 12,
    marginBottom: 8,
  },
  routingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
    borderBottomWidth: 1,
    borderBottomColor: '#222',
  },
  routingRole: {
    color: '#ccc',
    fontSize: 12,
    flex: 2,
  },
  routingModel: {
    color: '#4a90e2',
    fontSize: 12,
    flex: 3,
    textAlign: 'center',
  },
  routingTemp: {
    color: '#ff9800',
    fontSize: 12,
    flex: 1,
    textAlign: 'right',
  },
  routingHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 8,
  },
  benchmarkBtn: {
    backgroundColor: '#4a90e2',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 6,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  benchmarkBtnText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 12,
  },
  benchmarkProgressBox: {
    backgroundColor: '#0d0d1f',
    borderRadius: 6,
    padding: 10,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: '#333',
  },
  benchmarkBar: {
    height: 6,
    backgroundColor: '#222',
    borderRadius: 3,
    overflow: 'hidden',
    marginBottom: 4,
  },
  benchmarkBarFill: {
    height: '100%',
    backgroundColor: '#4a90e2',
    borderRadius: 3,
  },
  benchmarkPercentText: {
    color: '#4a90e2',
    fontSize: 11,
    textAlign: 'right',
    marginBottom: 6,
  },
  benchmarkLog: {
    maxHeight: 160,
  },
  benchmarkLogMsg: {
    color: '#aaa',
    fontSize: 11,
    lineHeight: 16,
  },
  benchmarkError: {
    color: '#f44336',
    fontSize: 12,
    marginVertical: 6,
  },
});


