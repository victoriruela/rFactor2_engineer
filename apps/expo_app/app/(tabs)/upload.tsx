import { useState, useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, Platform, ScrollView, ActivityIndicator } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import { uploadFile, getSetup, loadSessionTelemetry, setSessionState, getClientSessionId, overrideClientSessionId } from '../../src/api';
import type { SetupChange, AnalysisResponse } from '../../src/api';
import SetupCompleteSection from '../../src/components/SetupCompleteSection';
import LockedParametersPanel from '../../src/components/LockedParametersPanel';

// ── File helpers (web-only: download / pick JSON) ──

function downloadJSON(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function pickJSONFile(): Promise<unknown | null> {
  return new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    // Fired in modern browsers when the dialog is closed without selecting a file
    input.addEventListener('cancel', () => resolve(null));
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) { resolve(null); return; }
      const reader = new FileReader();
      reader.onload = () => {
        try { resolve(JSON.parse(reader.result as string)); }
        catch { reject(new Error('Archivo JSON inválido')); }
      };
      reader.onerror = () => reject(new Error('Error leyendo archivo'));
      reader.readAsText(file);
    };
    input.click();
  });
}

// ── Session / locked-params file formats ──

interface SessionFile {
  version: 1;
  session_id: string;
  client_session_id?: string;
  saved_at: string;
  analysis_result: AnalysisResponse | null;
  full_setup: Record<string, SetupChange[]> | null;
  locked_parameters: string[];
}

interface LockedParamsFile {
  version: 1;
  saved_at: string;
  locked_parameters: string[];
}

export default function DatosScreen() {
  const {
    telemetryFile, svmFile,
    setTelemetryFile, setSvmFile,
    uploadProgress, setUploadProgress,
    isUploading, setUploading,
    activeSessionId, setActiveSessionId,
    analysisResult, setAnalysisResult,
    fullSetup, setFullSetup,
    lockedParameters, setLockedParameters,
  } = useAppStore();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);

  const hasSession = Boolean(activeSessionId && (analysisResult || fullSetup));

  // ── Pick telemetry / svm files ──
  const pickFile = useCallback(async (type: 'telemetry' | 'svm') => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = type === 'telemetry' ? '.mat,.csv' : '.svm';
      input.onchange = () => {
        const file = input.files?.[0];
        if (file) {
          type === 'telemetry' ? setTelemetryFile(file) : setSvmFile(file);
        }
      };
      input.click();
    }
  }, [setTelemetryFile, setSvmFile]);

  // ── Upload files to server ──
  const handleUpload = useCallback(async () => {
    if (!telemetryFile || !svmFile) {
      setError('Selecciona ambos archivos');
      return;
    }

    setUploading(true);
    setError(null);
    setSuccess(null);
    setUploadProgress(0);

    try {
      const telemetrySessionId = await uploadFile(telemetryFile, (pct) => setUploadProgress(pct / 2));
      const svmSessionId = await uploadFile(svmFile, (pct) => setUploadProgress(50 + pct / 2));

      if (telemetrySessionId !== svmSessionId) {
        throw new Error('Los archivos subidos no quedaron asociados a la misma sesión');
      }

      setActiveSessionId(svmSessionId);
      setSessionState(svmSessionId, 'uploaded');

      const telemetryPayload = await loadSessionTelemetry(svmSessionId);
      setAnalysisResult(telemetryPayload);
      setSessionState(svmSessionId, 'telemetry_loaded');

      const setup = await getSetup(svmSessionId);
      setFullSetup(setup);

      setSuccess('Archivos subidos correctamente');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de subida';
      setError(msg);
    } finally {
      setUploading(false);
    }
  }, [
    telemetryFile, svmFile, setUploading, setUploadProgress,
    setActiveSessionId, setAnalysisResult, setFullSetup,
  ]);

  // ── Save session to local file ──
  const handleSaveSession = useCallback(() => {
    if (!hasSession) return;
    const sessionFile: SessionFile = {
      version: 1,
      session_id: activeSessionId!,
      client_session_id: getClientSessionId(),
      saved_at: new Date().toISOString(),
      analysis_result: analysisResult,
      full_setup: fullSetup,
      locked_parameters: Array.from(lockedParameters),
    };
    const safeName = (activeSessionId ?? 'session').replace(/[^a-zA-Z0-9_\-]/g, '_');
    const filename = `session_${safeName}_${new Date().toISOString().slice(0, 10)}.json`;
    downloadJSON(sessionFile, filename);
    setSuccess('Sesión guardada en archivo');
  }, [hasSession, activeSessionId, analysisResult, fullSetup, lockedParameters]);

  // ── Load session from local file ──
  const handleLoadSession = useCallback(async () => {
    setError(null);
    setSuccess(null);
    setLoadingSession(true);
    try {
      const data = await pickJSONFile() as SessionFile | null;
      if (data === null) return;
      if (!data || data.version !== 1) {
        throw new Error('Formato de archivo de sesión no reconocido');
      }
      if (data.analysis_result) setAnalysisResult(data.analysis_result);
      if (data.full_setup) setFullSetup(data.full_setup);
      if (data.client_session_id) overrideClientSessionId(data.client_session_id);
      if (data.session_id) setActiveSessionId(data.session_id);
      if (Array.isArray(data.locked_parameters)) {
        setLockedParameters(new Set(data.locked_parameters));
      }
      setSuccess('Sesión cargada desde archivo');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error al cargar sesión';
      setError(msg);
    } finally {
      setLoadingSession(false);
    }
  }, [setAnalysisResult, setFullSetup, setActiveSessionId, setLockedParameters]);

  // ── Save locked params to local file ──
  const handleSaveLockedParams = useCallback(() => {
    if (lockedParameters.size === 0) return;
    const file: LockedParamsFile = {
      version: 1,
      saved_at: new Date().toISOString(),
      locked_parameters: Array.from(lockedParameters),
    };
    downloadJSON(file, `locked_params_${new Date().toISOString().slice(0, 10)}.json`);
    setSuccess('Parámetros fijados guardados en archivo');
  }, [lockedParameters]);

  // ── Load locked params from local file ──
  const handleLoadLockedParams = useCallback(async () => {
    setError(null);
    setSuccess(null);
    try {
      const data = await pickJSONFile() as LockedParamsFile | null;
      if (data === null) return;
      if (!data || data.version !== 1 || !Array.isArray(data.locked_parameters)) {
        throw new Error('Formato de archivo de parámetros no reconocido');
      }
      // Filter to only params that exist in current setup
      const availableParams = new Set(
        Object.values(fullSetup ?? {})
          .flatMap((items) => items.map((item) => item.parameter))
          .filter((p) => typeof p === 'string' && p.trim().length > 0),
      );
      const validParams = data.locked_parameters.filter((p: string) => availableParams.has(p));
      setLockedParameters(new Set(validParams));
      const skipped = data.locked_parameters.length - validParams.length;
      setSuccess(
        `Parámetros fijados cargados (${validParams.length} aplicados` +
        (skipped > 0 ? `, ${skipped} ignorados por no existir en el setup actual` : '') +
        ')',
      );
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error al cargar parámetros';
      setError(msg);
    }
  }, [fullSetup, setLockedParameters]);

  // ── Derived data ──
  const sessionStats = analysisResult?.session_stats;

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>Datos</Text>

      {/* ── Upload section ── */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Subir Archivos</Text>

        <Pressable style={styles.pickBtn} onPress={() => pickFile('telemetry')}>
          <Text style={styles.pickText}>
            {telemetryFile ? `📊 ${telemetryFile.name}` : 'Seleccionar telemetría (.mat/.csv)'}
          </Text>
        </Pressable>

        <Pressable style={styles.pickBtn} onPress={() => pickFile('svm')}>
          <Text style={styles.pickText}>
            {svmFile ? `🔧 ${svmFile.name}` : 'Seleccionar setup (.svm)'}
          </Text>
        </Pressable>

        {isUploading ? (
          <View style={styles.progressContainer}>
            <View style={[styles.progressBar, { width: `${uploadProgress}%` }]} />
            <Text style={styles.progressText}>{Math.round(uploadProgress)}%</Text>
          </View>
        ) : (
          <Pressable
            style={[styles.uploadBtn, (!telemetryFile || !svmFile) && styles.disabled]}
            onPress={handleUpload}
            disabled={!telemetryFile || !svmFile}
          >
            <Text style={styles.btnText}>Subir Archivos</Text>
          </Pressable>
        )}
      </View>

      {/* ── Session management ── */}
      <View style={styles.card}>
        <Text style={styles.cardTitle}>Gestión de Sesión</Text>
        <View style={styles.buttonRow}>
          <Pressable style={[styles.actionBtn, styles.loadBtn]} onPress={handleLoadSession} disabled={loadingSession}>
            {loadingSession
              ? <ActivityIndicator size="small" color="#fff" />
              : <Text style={styles.btnText}>Cargar Sesión</Text>}
          </Pressable>
          <Pressable
            style={[styles.actionBtn, styles.saveBtn, !hasSession && styles.disabled]}
            onPress={handleSaveSession}
            disabled={!hasSession}
          >
            <Text style={styles.btnText}>Guardar Sesión</Text>
          </Pressable>
        </View>
      </View>

      {/* ── Locked params management (only when session loaded) ── */}
      {hasSession && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Parámetros Fijados</Text>
          <View style={styles.buttonRow}>
            <Pressable style={[styles.actionBtn, styles.loadBtn]} onPress={handleLoadLockedParams}>
              <Text style={styles.btnText}>Cargar Fijados</Text>
            </Pressable>
            <Pressable
              style={[styles.actionBtn, styles.saveBtn, lockedParameters.size === 0 && styles.disabled]}
              onPress={handleSaveLockedParams}
              disabled={lockedParameters.size === 0}
            >
              <Text style={styles.btnText}>Guardar Fijados</Text>
            </Pressable>
          </View>
        </View>
      )}

      {/* ── Status messages ── */}
      {error && <Text style={styles.error}>{error}</Text>}
      {success && <Text style={styles.success}>{success}</Text>}

      {/* ── Session info ── */}
      {hasSession && sessionStats && (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Información de Sesión</Text>
          {sessionStats.circuit_name ? (
            <Text style={styles.infoText}>Circuito: {sessionStats.circuit_name}</Text>
          ) : null}
          <Text style={styles.infoText}>Vueltas: {sessionStats.total_laps}</Text>
          <Text style={styles.infoText}>
            Mejor vuelta: {sessionStats.best_lap_time > 0
              ? `${Math.floor(sessionStats.best_lap_time / 60)}:${(sessionStats.best_lap_time % 60).toFixed(3).padStart(6, '0')}`
              : '--'}
          </Text>
          <Text style={styles.infoText}>
            Vuelta media: {sessionStats.avg_lap_time > 0
              ? `${Math.floor(sessionStats.avg_lap_time / 60)}:${(sessionStats.avg_lap_time % 60).toFixed(3).padStart(6, '0')}`
              : '--'}
          </Text>
        </View>
      )}

      {/* ── Setup + Locked Params (two columns) ── */}
      {fullSetup && (
        <View style={styles.twoColumnContainer}>
          <View style={styles.column}>
            <SetupCompleteSection fullSetup={fullSetup} />
          </View>
          <View style={styles.column}>
            <LockedParametersPanel fullSetup={fullSetup} />
          </View>
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
    alignItems: 'stretch',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 24,
  },
  card: {
    backgroundColor: '#1a1a3e',
    padding: 16,
    borderRadius: 8,
    marginBottom: 16,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 12,
  },
  pickBtn: {
    backgroundColor: '#0d0d1f',
    paddingVertical: 14,
    paddingHorizontal: 20,
    borderRadius: 8,
    marginBottom: 10,
    borderWidth: 1,
    borderColor: '#333',
    borderStyle: 'dashed',
  },
  pickText: {
    color: '#ccc',
    textAlign: 'center',
    fontSize: 14,
  },
  uploadBtn: {
    backgroundColor: '#e53935',
    paddingVertical: 12,
    paddingHorizontal: 32,
    borderRadius: 8,
    marginTop: 8,
    alignItems: 'center',
  },
  progressContainer: {
    width: '100%',
    height: 32,
    backgroundColor: '#0d0d1f',
    borderRadius: 8,
    marginTop: 8,
    overflow: 'hidden',
    justifyContent: 'center',
  },
  progressBar: {
    position: 'absolute',
    left: 0,
    top: 0,
    bottom: 0,
    backgroundColor: '#e53935',
    borderRadius: 8,
  },
  progressText: {
    color: '#fff',
    textAlign: 'center',
    fontWeight: 'bold',
    zIndex: 1,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 10,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 44,
  },
  loadBtn: {
    backgroundColor: '#1565c0',
  },
  saveBtn: {
    backgroundColor: '#2e7d32',
  },
  disabled: {
    opacity: 0.4,
  },
  btnText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 14,
  },
  error: {
    color: '#f44336',
    marginBottom: 12,
    fontSize: 13,
  },
  success: {
    color: '#4caf50',
    marginBottom: 12,
    fontSize: 13,
  },
  infoText: {
    color: '#ccc',
    fontSize: 13,
    marginBottom: 4,
  },
  twoColumnContainer: {
    flexDirection: 'row',
    gap: 16,
    marginTop: 8,
  },
  column: {
    flex: 1,
  },
});
