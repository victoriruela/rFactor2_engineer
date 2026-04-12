import { useState, useCallback, useEffect } from 'react';
import { View, Text, StyleSheet, Pressable, Platform, ScrollView, ActivityIndicator } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import { buildPreparsedPayloadFromFiles } from '../../src/utils/preparsedClientPayload';
import type { SetupChange, AnalysisResponse, PreparsedAnalyzePayload } from '../../src/api';
import SetupCompleteSection from '../../src/components/SetupCompleteSection';
import LockedParametersPanel from '../../src/components/LockedParametersPanel';
import { gzip, ungzip } from 'pako';

// ── File helpers (web-only: download / pick) ──

function downloadCompressed(data: unknown, filename: string): void {
  const json = JSON.stringify(data);
  const compressed = gzip(json);
  const blob = new Blob([compressed], { type: 'application/gzip' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function downloadJSON(data: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function pickSessionFile(): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.rf2session,.json';
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) { reject(new Error('No se seleccionó archivo')); return; }
      const reader = new FileReader();
      reader.onload = () => {
        try {
          const buf = new Uint8Array(reader.result as ArrayBuffer);
          // Detect gzip magic bytes (0x1f 0x8b)
          if (buf.length >= 2 && buf[0] === 0x1f && buf[1] === 0x8b) {
            const decompressed = ungzip(buf, { to: 'string' });
            resolve(JSON.parse(decompressed));
          } else {
            // Legacy uncompressed JSON
            const text = new TextDecoder().decode(buf);
            resolve(JSON.parse(text));
          }
        } catch { reject(new Error('Archivo inválido (no se pudo descomprimir ni leer como JSON)')); }
      };
      reader.onerror = () => reject(new Error('Error leyendo archivo'));
      reader.readAsArrayBuffer(file);
    };
    input.click();
  });
}

function pickJSONFile(): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = () => {
      const file = input.files?.[0];
      if (!file) { reject(new Error('No se seleccionó archivo')); return; }
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
  version: 1 | 2;
  session_id: string;
  saved_at: string;
  analysis_result: AnalysisResponse | null;
  full_setup: Record<string, SetupChange[]> | null;
  locked_parameters: string[];
  preparsed_payload?: PreparsedAnalyzePayload | null; // v2+
}

interface LockedParamsFile {
  version: 1;
  saved_at: string;
  locked_parameters: string[];
}

function buildSelectedFilesKey(telemetryFile: File | null, svmFile: File | null): string | null {
  if (!telemetryFile || !svmFile) return null;
  return [
    telemetryFile.name,
    telemetryFile.size,
    telemetryFile.lastModified,
    svmFile.name,
    svmFile.size,
    svmFile.lastModified,
  ].join('|');
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
    preparsedPayload, setPreparsedPayload,
    lockedParameters, setLockedParameters,
  } = useAppStore();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [lastProcessedFilesKey, setLastProcessedFilesKey] = useState<string | null>(null);

  const hasSession = Boolean(activeSessionId && (analysisResult || fullSetup));

  // ── Pick telemetry / svm files ──
  const getBaseName = (f: File) => f.name.replace(/\.[^.]+$/, '');

  const pickFile = useCallback(async (type: 'telemetry' | 'svm') => {
    if (Platform.OS === 'web') {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = type === 'telemetry' ? '.ld' : '.svm';
      input.onchange = () => {
        const file = input.files?.[0];
        if (!file) return;
        if (type === 'telemetry') {
          if (svmFile && getBaseName(file) !== getBaseName(svmFile)) {
            setError(`El archivo .ld ("${getBaseName(file)}") no coincide con el .svm ya seleccionado ("${getBaseName(svmFile)}"). Deben tener el mismo nombre.`);
            setSvmFile(null);
          } else {
            setError(null);
          }
          setTelemetryFile(file);
        } else {
          if (telemetryFile && getBaseName(file) !== getBaseName(telemetryFile)) {
            setError(`El archivo .svm ("${getBaseName(file)}") no coincide con el .ld ya seleccionado ("${getBaseName(telemetryFile)}"). Deben tener el mismo nombre.`);
            return; // reject the wrong svm
          }
          setError(null);
          setSvmFile(file);
        }
      };
      input.click();
    }
  }, [setTelemetryFile, setSvmFile, telemetryFile, svmFile]);

  // ── Parse files in browser and store preparsed payload ──
  const processSelectedFiles = useCallback(async (isAutomatic: boolean) => {
    if (!telemetryFile || !svmFile) {
      setError('Selecciona ambos archivos');
      return;
    }
    if (telemetryFile.name.replace(/\.[^.]+$/, '') !== svmFile.name.replace(/\.[^.]+$/, '')) {
      setError(`Los archivos deben tener el mismo nombre: "${telemetryFile.name.replace(/\.[^.]+$/, '')}" ≠ "${svmFile.name.replace(/\.[^.]+$/, '')}".`);
      return;
    }

    const selectedFilesKey = buildSelectedFilesKey(telemetryFile, svmFile);
    if (!selectedFilesKey) {
      setError('Selecciona ambos archivos');
      return;
    }

    setUploading(true);
    setError(null);
    setSuccess(null);
    setUploadProgress(0);

    try {
      setUploadProgress(15);
      const parsed = await buildPreparsedPayloadFromFiles(telemetryFile, svmFile);

      const localSessionId = `local-${Date.now().toString(36)}`;
      setActiveSessionId(localSessionId);
      setPreparsedPayload(parsed.payload);
      setUploadProgress(80);

      setFullSetup(parsed.fullSetup);
      setAnalysisResult({
        circuit_data: parsed.preview.circuit_data,
        issues_on_map: [],
        driving_analysis: '',
        telemetry_analysis: '',
        setup_analysis: {},
        full_setup: parsed.fullSetup,
        session_stats: parsed.preview.session_stats,
        laps_data: parsed.preview.laps_data,
        agent_reports: [],
        telemetry_summary_sent: parsed.preview.telemetry_summary_sent,
        chief_reasoning: '',
        telemetry_series: parsed.preview.telemetry_series,
      });

      setUploadProgress(100);
      setLastProcessedFilesKey(selectedFilesKey);
      setSuccess(isAutomatic ? 'Archivos procesados automaticamente y listos para analizar' : 'Archivos reprocesados correctamente');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : (typeof e === 'string' ? e : String(e));
      setError(msg);
    } finally {
      setUploading(false);
    }
  }, [
    telemetryFile, svmFile, setUploading, setUploadProgress,
    setActiveSessionId, setAnalysisResult, setFullSetup, setPreparsedPayload,
    setLastProcessedFilesKey,
  ]);

  const handleUpload = useCallback(async () => {
    await processSelectedFiles(false);
  }, [processSelectedFiles]);

  useEffect(() => {
    const selectedFilesKey = buildSelectedFilesKey(telemetryFile, svmFile);
    if (!selectedFilesKey) {
      setLastProcessedFilesKey(null);
      return;
    }
    if (isUploading || selectedFilesKey === lastProcessedFilesKey) return;
    void processSelectedFiles(true);
  }, [telemetryFile, svmFile, isUploading, lastProcessedFilesKey, processSelectedFiles]);

  // ── Save session to local file ──
  const handleSaveSession = useCallback(() => {
    if (!hasSession) return;
    const sessionFile: SessionFile = {
      version: 2,
      session_id: activeSessionId!,
      saved_at: new Date().toISOString(),
      analysis_result: analysisResult,
      full_setup: fullSetup,
      locked_parameters: Array.from(lockedParameters),
      preparsed_payload: preparsedPayload,
    };
    const baseName = telemetryFile
      ? telemetryFile.name.replace(/\.ld$/i, '')
      : (activeSessionId ?? 'session').replace(/[^a-zA-Z0-9_\- .]/g, '_');
    const filename = `${baseName}_${new Date().toISOString().slice(0, 10)}.rf2session`;
    downloadCompressed(sessionFile, filename);
    setSuccess('Sesión guardada en archivo comprimido');
  }, [hasSession, activeSessionId, analysisResult, fullSetup, lockedParameters, preparsedPayload, telemetryFile]);

  // ── Load session from local file ──
  const handleLoadSession = useCallback(async () => {
    setError(null);
    setSuccess(null);
    setLoadingSession(true);
    try {
      const data = await pickSessionFile() as SessionFile;
      if (!data || (data.version !== 1 && data.version !== 2)) {
        throw new Error('Formato de archivo de sesión no reconocido');
      }
      if (data.analysis_result) setAnalysisResult(data.analysis_result);
      if (data.full_setup) setFullSetup(data.full_setup);
      if (data.session_id) setActiveSessionId(data.session_id);
      if (Array.isArray(data.locked_parameters)) {
        setLockedParameters(new Set(data.locked_parameters));
      }
      // Restore preparsed payload (v2+) so the user can re-analyze
      if (data.preparsed_payload) {
        setPreparsedPayload(data.preparsed_payload);
      }
      setSuccess('Sesión cargada desde archivo');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error al cargar sesión';
      setError(msg);
    } finally {
      setLoadingSession(false);
    }
  }, [setAnalysisResult, setFullSetup, setActiveSessionId, setLockedParameters, setPreparsedPayload]);

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
      const data = await pickJSONFile() as LockedParamsFile;
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
            {telemetryFile ? `📊 ${telemetryFile.name}` : 'Seleccionar telemetría (.ld)'}
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
            <Text style={styles.btnText}>Reprocesar Archivos</Text>
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
