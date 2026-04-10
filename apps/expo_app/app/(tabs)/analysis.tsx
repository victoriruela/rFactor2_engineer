import { useCallback, useEffect, useMemo, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import { analyzeFiles, analyzeSessionStream, getSetup, listModels, listSessions, setSessionState } from '../../src/api';
import type { ProgressEvent, SetupChange } from '../../src/api';
import SetupTable from '../../src/components/SetupTable';
import MarkdownText from '../../src/components/MarkdownText';
import ChiefReasoningFormatter from '../../src/components/ChiefReasoningFormatter';
import TelemetryExpertAnalysisFormatter from '../../src/components/TelemetryExpertAnalysisFormatter';
import { toSpanishParameterName } from '../../src/utils/labelTranslator';

const AGENT_LABELS: Record<string, string> = {
  driving: 'Análisis de conducción',
  telemetry: 'Experto de telemetría',
  specialist: 'Especialista de setup',
  chief: 'Ingeniero jefe',
};

function formatLapTime(seconds: number): string {
  if (seconds <= 0) return '--';
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toFixed(3).padStart(6, '0')}`;
}

export default function AnalysisScreen() {
  const {
    telemetryFile, svmFile,
    isAnalyzing, setAnalyzing,
    analysisResult, setAnalysisResult,
    analysisError, setAnalysisError,
    models, setModels,
    selectedModel, setSelectedModel,
    selectedProvider,
    lockedParameters,
    activeSessionId,
    setActiveSessionId,
    fullSetup,
    setFullSetup,
  } = useAppStore();
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [modelsRefreshing, setModelsRefreshing] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [progressMessages, setProgressMessages] = useState<ProgressEvent[]>([]);
  const [progressExpanded, setProgressExpanded] = useState(true);

  const refreshModels = useCallback(async () => {
    setModelsRefreshing(true);
    setModelsError(null);
    try {
      const m = await listModels();
      setModels(m);
      setModelsLoaded(true);
      if (m.length === 0) {
        setModelsError('No se encontraron modelos en Ollama.');
      }
    } catch {
      setModelsLoaded(true);
      setModelsError('No se pudieron cargar los modelos de Ollama.');
    } finally {
      setModelsRefreshing(false);
    }
  }, [setModels]);

  useEffect(() => {
    void refreshModels();
  }, [refreshModels]);

  useEffect(() => {
    // Ensure setup is available for analysis (needed for locked params filtering)
    if (!activeSessionId || fullSetup) {
      return;
    }
    getSetup(activeSessionId)
      .then((setup) => setFullSetup(setup))
      .catch(() => {
        // Ignore setup preload errors; user can still run analysis.
      });
  }, [activeSessionId, fullSetup, setFullSetup]);

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
    // Check if we can start analysis with an existing session or fresh upload
    let targetSessionId = activeSessionId;
    const hasLocalFiles = telemetryFile && svmFile;

    if (!hasLocalFiles && !targetSessionId) {
      // No local files and no existing session → require upload
      setAnalysisError('Sube ambos archivos primero en la pestaña "Subida"');
      return;
    }

    // If no local files but session exists, try to use the session ID
    if (!hasLocalFiles && targetSessionId) {
      // Session is already loaded; we can proceed with analysis
    } else if (!targetSessionId) {
      // We have local files but no session ID yet, try to find one
      try {
        const availableSessions = await listSessions();
        targetSessionId = availableSessions[0]?.id ?? null;
      } catch (e) {
        // If no session found, we'll use direct file upload below
        targetSessionId = null;
      }
    }

    setAnalyzing(true);
    setAnalysisError(null);
    setProgressMessages([]);
    setProgressExpanded(true);

    try {
      if (targetSessionId) {
        setActiveSessionId(targetSessionId);
        // Use streaming endpoint with existing session
        const result = await analyzeSessionStream(
          targetSessionId,
          selectedModel,
          selectedProvider,
          Array.from(lockedParameters),
          (ev) => setProgressMessages((prev) => [...prev, ev]),
        );
        setAnalysisResult(result);
        setSessionState(targetSessionId, 'analysis_complete');
        // Minimize progress when analysis completes
        setProgressExpanded(false);
      } else if (hasLocalFiles) {
        // Fallback: direct multipart with uploaded files
        setProgressMessages([{ type: 'progress', agent: 'driving', message: 'Enviando archivos y analizando...' }]);
        const result = await analyzeFiles(telemetryFile, svmFile, selectedModel, selectedProvider, Array.from(lockedParameters));
        setAnalysisResult(result);
        setProgressExpanded(false);
      } else {
        // Should not reach here, but handle edge case
        throw new Error('No session or files available for analysis');
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error en el análisis';
      setAnalysisError(msg);
    } finally {
      setAnalyzing(false);
    }
  }, [
    telemetryFile,
    svmFile,
    selectedModel,
    selectedProvider,
    lockedParameters,
    activeSessionId,
    setActiveSessionId,
    setAnalyzing,
    setAnalysisResult,
    setAnalysisError,
  ]);

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>Análisis AI</Text>

      {/* Model selector */}
      <View style={styles.modelHeaderRow}>
        <Text style={styles.label}>Modelos de Ollama:</Text>
        <Pressable
          style={[styles.refreshBtn, modelsRefreshing && styles.disabled]}
          onPress={refreshModels}
          disabled={modelsRefreshing}
        >
          <Text style={styles.refreshBtnText}>{modelsRefreshing ? 'Refrescando...' : 'Refrescar modelos'}</Text>
        </Pressable>
      </View>

      {modelsLoaded && models.length > 0 ? (
        <View style={styles.modelRow}>
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
      ) : null}

      {modelsError ? <Text style={styles.modelError}>{modelsError}</Text> : null}

      <View style={styles.modelConfigRow}>
        <Text style={styles.label}>Modelo (manual):</Text>
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
                  <Text style={styles.progressMsg}> Procesando...</Text>
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
    marginBottom: 10,
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
});


