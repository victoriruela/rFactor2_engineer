import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator, TextInput } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import { analyzeFiles, analyzeSessionStream, listModels, listSessions, setSessionState } from '../../src/api';
import type { ProgressEvent } from '../../src/api';
import SetupTable from '../../src/components/SetupTable';
import MarkdownText from '../../src/components/MarkdownText';
import ChiefReasoningFormatter from '../../src/components/ChiefReasoningFormatter';
import SetupCompleteSection from '../../src/components/SetupCompleteSection';
import LockedParametersPanel from '../../src/components/LockedParametersPanel';

const AGENT_LABELS: Record<string, string> = {
  driving: 'Análisis de conducción',
  specialist: 'Especialista de setup',
  chief: 'Ingeniero jefe',
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
    lockedParameters,
    activeSessionId,
    setActiveSessionId,
  } = useAppStore();
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [progressMessages, setProgressMessages] = useState<ProgressEvent[]>([]);
  const [progressExpanded, setProgressExpanded] = useState(true);

  useEffect(() => {
    listModels()
      .then((m) => { setModels(m); setModelsLoaded(true); })
      .catch(() => setModelsLoaded(true));
  }, [setModels]);

  const handleAnalyze = useCallback(async () => {
    if (!telemetryFile || !svmFile) {
      setAnalysisError('Sube ambos archivos primero en la pestaña "Upload"');
      return;
    }

    setAnalyzing(true);
    setAnalysisError(null);
    setProgressMessages([]);
    setProgressExpanded(true);

    try {
      let targetSessionId = activeSessionId;
      if (!targetSessionId) {
        const availableSessions = await listSessions();
        targetSessionId = availableSessions[0]?.id ?? null;
      }

      if (targetSessionId) {
        setActiveSessionId(targetSessionId);
        // Use streaming endpoint
        const result = await analyzeSessionStream(
          targetSessionId,
          selectedModel,
          selectedProvider,
          (ev) => setProgressMessages((prev) => [...prev, ev]),
        );
        setAnalysisResult(result);
        setSessionState(targetSessionId, 'analysis_complete');
        // Minimize progress when analysis completes
        setProgressExpanded(false);
      } else {
        // Fallback: direct multipart (no streaming)
        setProgressMessages([{ type: 'progress', agent: 'driving', message: 'Enviando archivos y analizando...' }]);
        const result = await analyzeFiles(telemetryFile, svmFile, selectedModel, selectedProvider);
        setAnalysisResult(result);
        setProgressExpanded(false);
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
          <Text style={styles.analyzeBtnText}>Iniciar Análisis</Text>
        )}
      </Pressable>

      {analysisError && <Text style={styles.error}>{analysisError}</Text>}

      {/* Locked parameters panel */}
      {analysisResult?.full_setup && (
        <View style={styles.section}>
          <LockedParametersPanel fullSetup={analysisResult.full_setup} />
        </View>
      )}

      {/* Setup completo section */}
      {analysisResult?.full_setup && (
        <View style={styles.section}>
          <SetupCompleteSection fullSetup={analysisResult.full_setup} />
        </View>
      )}

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
                  <Text style={styles.statValue}>{analysisResult.session_stats.best_lap_time.toFixed(3)}s</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={styles.statLabel}>Vuelta Media</Text>
                  <Text style={styles.statValue}>{analysisResult.session_stats.avg_lap_time.toFixed(3)}s</Text>
                </View>
              </View>
            </View>
          )}

          {/* Driving Analysis - markdown rendered */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Análisis de Conducción</Text>
            <MarkdownText text={analysisResult.driving_analysis} />
          </View>

          {/* Chief reasoning - formatted nicely */}
          {analysisResult.chief_reasoning ? (
            <View style={styles.section}>
              <ChiefReasoningFormatter reasoning={analysisResult.chief_reasoning} />
            </View>
          ) : null}

          {/* Setup Recommendations */}
          {Object.values(analysisResult.setup_analysis).some((items) => items.length > 0) ? (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Recomendaciones de Setup</Text>
              {lockedParameters.size > 0 && (
                <View style={styles.lockedNotice}>
                  <Text style={styles.lockedNoticeText}>
                    Parámetros fijados: {Array.from(lockedParameters).join(', ')}
                  </Text>
                </View>
              )}
              <SetupTable changes={analysisResult.setup_analysis} />
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


