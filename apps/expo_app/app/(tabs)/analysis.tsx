import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import { analyzeFiles, analyzeSessionStream, listModels, listSessions } from '../../src/api';
import type { GPSPoint, ProgressEvent } from '../../src/api';
import CircuitMap from '../../src/components/CircuitMap';
import SetupTable from '../../src/components/SetupTable';
import MarkdownText from '../../src/components/MarkdownText';
import TelemetryCharts from '../../src/components/TelemetryCharts';

const AGENT_LABELS: Record<string, string> = {
  driving: 'ðŸŽ AnÃ¡lisis de conducciÃ³n',
  specialist: 'ðŸ”§ Especialista de setup',
  chief: 'ðŸ‘¨â€ðŸ’¼ Ingeniero jefe',
};

export default function AnalysisScreen() {
  const {
    telemetryFile, svmFile,
    isAnalyzing, setAnalyzing,
    analysisResult, setAnalysisResult,
    analysisError, setAnalysisError,
    models, setModels,
    selectedModel, setSelectedModel,
    selectedProvider,
  } = useAppStore();
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [progressMessages, setProgressMessages] = useState<ProgressEvent[]>([]);
  const [cursorPosition, setCursorPosition] = useState<GPSPoint | null>(null);

  useEffect(() => {
    listModels()
      .then((m) => { setModels(m); setModelsLoaded(true); })
      .catch(() => setModelsLoaded(true));
  }, [setModels]);

  const handleAnalyze = useCallback(async () => {
    if (!telemetryFile || !svmFile) {
      setAnalysisError('Sube ambos archivos primero en la pestaÃ±a Upload');
      return;
    }

    setAnalyzing(true);
    setAnalysisError(null);
    setProgressMessages([]);
    setCursorPosition(null);

    try {
      const availableSessions = await listSessions();
      const targetSession = availableSessions[0];

      if (targetSession) {
        // Use streaming endpoint
        const result = await analyzeSessionStream(
          targetSession.id,
          selectedModel,
          selectedProvider,
          (ev) => setProgressMessages((prev) => [...prev, ev]),
        );
        setAnalysisResult(result);
      } else {
        // Fallback: direct multipart (no streaming)
        setProgressMessages([{ type: 'progress', agent: 'driving', message: 'Enviando archivos y analizando...' }]);
        const result = await analyzeFiles(telemetryFile, svmFile, selectedModel, selectedProvider);
        setAnalysisResult(result);
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error en el anÃ¡lisis';
      setAnalysisError(msg);
    } finally {
      setAnalyzing(false);
    }
  }, [telemetryFile, svmFile, selectedModel, selectedProvider, setAnalyzing, setAnalysisResult, setAnalysisError]);

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

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>AnÃ¡lisis AI</Text>

      {/* Model selector */}
      {modelsLoaded && models.length > 0 && (
        <View style={styles.modelRow}>
          <Text style={styles.label}>Modelo:</Text>
          <View style={styles.modelList}>
            {models.map((m) => (
              <Pressable
                key={m.name}
                style={[styles.modelChip, selectedModel === m.name && styles.modelChipActive]}
                onPress={() => setSelectedModel(m.name)}
              >
                <Text style={[styles.modelChipText, selectedModel === m.name && styles.modelChipTextActive]}>
                  {m.name}
                </Text>
              </Pressable>
            ))}
          </View>
        </View>
      )}

      <View style={styles.modelConfigRow}>
        <Text style={styles.label}>Modelo manual:</Text>
        <TextInput
          style={styles.modelInput}
          value={selectedModel}
          onChangeText={setSelectedModel}
          placeholder="llama3.2:latest"
          placeholderTextColor="#777"
          autoCapitalize="none"
          autoCorrect={false}
        />
      </View>

      {/* Analyze button */}
      <Pressable
        style={[styles.analyzeBtn, isAnalyzing && styles.disabled]}
        onPress={handleAnalyze}
        disabled={isAnalyzing}
      >
        {isAnalyzing ? (
          <ActivityIndicator color="#fff" />
        ) : (
          <Text style={styles.analyzeBtnText}>Iniciar AnÃ¡lisis</Text>
        )}
      </Pressable>

      {analysisError && <Text style={styles.error}>{analysisError}</Text>}

      {/* Real-time progress log */}
      {(isAnalyzing || progressMessages.length > 0) && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Progreso del anÃ¡lisis</Text>
          <View style={styles.progressBox}>
            {progressMessages.map((ev, i) => (
              <View key={i} style={styles.progressRow}>
                <Text style={styles.progressAgent}>
                  {AGENT_LABELS[ev.agent] ?? ev.agent}
                  {ev.section ? ` â€” ${ev.section}` : ''}
                </Text>
                <Text style={styles.progressMsg}>{ev.message}</Text>
              </View>
            ))}
            {isAnalyzing && (
              <View style={styles.progressRow}>
                <ActivityIndicator size="small" color="#e53935" />
                <Text style={styles.progressMsg}> Procesando...</Text>
              </View>
            )}
          </View>
        </View>
      )}

      {/* Results */}
      {analysisResult && (
        <>
          {/* Session Stats */}
          {analysisResult.session_stats && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>EstadÃ­sticas</Text>
              <Text style={styles.stat}>
                Vueltas: {analysisResult.session_stats.total_laps}
              </Text>
              <Text style={styles.stat}>
                Mejor vuelta: {analysisResult.session_stats.best_lap_time.toFixed(3)}s
              </Text>
              <Text style={styles.stat}>
                Media: {analysisResult.session_stats.avg_lap_time.toFixed(3)}s
              </Text>
            </View>
          )}

          {/* Telemetry charts + synchronized circuit map */}
          {analysisResult.telemetry_series?.length > 0 && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>TelemetrÃ­a</Text>
              <TelemetryCharts
                samples={analysisResult.telemetry_series}
                onIndexChange={handleCursorIndex}
              />
              {analysisResult.circuit_data?.length > 0 && (
                <View style={{ marginTop: 16 }}>
                  <CircuitMap
                    gpsPoints={analysisResult.circuit_data}
                    issues={analysisResult.issues_on_map}
                    currentPosition={cursorPosition}
                  />
                </View>
              )}
            </View>
          )}

          {/* Circuit map without telemetry (GPS only) */}
          {(!analysisResult.telemetry_series?.length || analysisResult.telemetry_series.length === 0) &&
            analysisResult.circuit_data?.length > 0 && (
              <View style={styles.section}>
                <Text style={styles.sectionTitle}>Mapa del Circuito</Text>
                <CircuitMap
                  gpsPoints={analysisResult.circuit_data}
                  issues={analysisResult.issues_on_map}
                  currentPosition={cursorPosition}
                />
              </View>
            )}

          {/* Driving Analysis â€” markdown rendered */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>AnÃ¡lisis de ConducciÃ³n</Text>
            <MarkdownText text={analysisResult.driving_analysis} />
          </View>

          {/* Chief reasoning */}
          {analysisResult.chief_reasoning ? (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Razonamiento del Ingeniero Jefe</Text>
              <MarkdownText text={analysisResult.chief_reasoning} />
            </View>
          ) : null}

          {/* Setup Recommendations */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Recomendaciones de Setup</Text>
            <SetupTable changes={analysisResult.setup_analysis} />
          </View>
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
    alignItems: 'center',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 24,
  },
  modelRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 16,
    flexWrap: 'wrap',
  },
  modelConfigRow: {
    width: '100%',
    maxWidth: 520,
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
  stat: {
    color: '#ccc',
    fontSize: 14,
    marginBottom: 4,
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
    color: '#e53935',
    fontSize: 12,
    fontWeight: '600',
    minWidth: 120,
  },
  progressMsg: {
    color: '#aaa',
    fontSize: 12,
    flex: 1,
  },
});

