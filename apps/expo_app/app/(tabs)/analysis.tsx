import { useCallback, useEffect, useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, ActivityIndicator } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import { analyzeFiles, listModels } from '../../src/api';
import CircuitMap from '../../src/components/CircuitMap';
import SetupTable from '../../src/components/SetupTable';

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

  useEffect(() => {
    listModels()
      .then((m) => { setModels(m); setModelsLoaded(true); })
      .catch(() => setModelsLoaded(true));
  }, [setModels]);

  const handleAnalyze = useCallback(async () => {
    if (!telemetryFile || !svmFile) {
      setAnalysisError('Sube ambos archivos primero en la pestaña Upload');
      return;
    }

    setAnalyzing(true);
    setAnalysisError(null);

    try {
      const result = await analyzeFiles(telemetryFile, svmFile, selectedModel, selectedProvider);
      setAnalysisResult(result);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error en el análisis';
      setAnalysisError(msg);
    } finally {
      setAnalyzing(false);
    }
  }, [telemetryFile, svmFile, selectedModel, selectedProvider, setAnalyzing, setAnalysisResult, setAnalysisError]);

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

      {/* Results */}
      {analysisResult && (
        <>
          {/* Circuit Map */}
          {analysisResult.circuit_data?.length > 0 && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Mapa del Circuito</Text>
              <CircuitMap
                gpsPoints={analysisResult.circuit_data}
                issues={analysisResult.issues_on_map}
              />
            </View>
          )}

          {/* Session Stats */}
          {analysisResult.session_stats && (
            <View style={styles.section}>
              <Text style={styles.sectionTitle}>Estadísticas</Text>
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

          {/* Driving Analysis */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Análisis de Conducción</Text>
            <Text style={styles.analysisText}>{analysisResult.driving_analysis}</Text>
          </View>

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
  analysisText: {
    color: '#ccc',
    fontSize: 14,
    lineHeight: 22,
  },
});
