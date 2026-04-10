import { useEffect, useState, useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, ActivityIndicator } from 'react-native';
import { useFocusEffect } from 'expo-router';
import { useAppStore } from '../../src/store/useAppStore';
import {
  listSessions,
  cleanup,
  deleteSession,
  loadSessionTelemetry,
  getSetup,
  getSessionStates,
  setSessionState,
  removeSessionState,
  clearAllSessionStates,
  getSessionSnapshot,
  saveSessionSnapshot,
  saveLastLockedParameters,
  removeSessionSnapshot,
  clearAllSessionSnapshots,
  type SessionInfo,
  type SessionState,
  type SessionSnapshot,
} from '../../src/api';

const STATE_LABELS: Record<SessionState, string> = {
  uploaded: 'Subido',
  telemetry_loaded: 'Telemetria cargada',
  analysis_complete: 'Analisis completo',
};

const STATE_COLORS: Record<SessionState, string> = {
  uploaded: '#555',
  telemetry_loaded: '#f9a825',
  analysis_complete: '#4caf50',
};

function telemetryName(telemetry: string): string {
  return telemetry.replace(/\.(mat|csv)$/i, '');
}

export default function SessionsScreen() {
  const {
    sessions,
    setSessions,
    activeSessionId,
    setActiveSessionId,
    analysisResult,
    setAnalysisResult,
    setAnalysisError,
    fullSetup,
    setFullSetup,
    lockedParameters,
    setLockedParameters,
  } = useAppStore();
  const [loading, setLoading] = useState(true);
  const [sessionStates, setSessionStatesLocal] = useState<Record<string, SessionState>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [loadedId, setLoadedId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [savedId, setSavedId] = useState<string | null>(null);
  const [savedSnapshots, setSavedSnapshots] = useState<Record<string, SessionSnapshot | null>>({});

  const hasLoadedData = Boolean(analysisResult || fullSetup);

  const refresh = useCallback(async () => {
    setLoading(true);
    setActionError(null);
    try {
      const data = await listSessions();
      setSessions(data);
      setSessionStatesLocal(getSessionStates());
      const snapshotMap: Record<string, SessionSnapshot | null> = {};
      for (const sess of data) {
        snapshotMap[sess.id] = getSessionSnapshot(sess.id);
      }
      setSavedSnapshots(snapshotMap);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'No se pudieron cargar las sesiones';
      setActionError(message);
    } finally {
      setLoading(false);
    }
  }, [setSessions]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  useFocusEffect(
    useCallback(() => {
      void refresh();
      return undefined;
    }, [refresh]),
  );

  useEffect(() => {
    if (!activeSessionId) return;
    const exists = sessions.some((s) => s.id === activeSessionId);
    if (!exists) {
      void refresh();
    }
  }, [activeSessionId, sessions, refresh]);

  // ── Save current loaded state for one backend session (overwrite) ──
  const handleSave = useCallback((sessionId: string) => {
    setSavedId(null);
    setActionError(null);

    if (activeSessionId !== sessionId || !hasLoadedData) {
      setActionError('Carga una sesion o estado primero para poder guardarlo.');
      return;
    }

    const state: SessionState = analysisResult ? 'analysis_complete' : 'telemetry_loaded';
    const snapshot: SessionSnapshot = {
      session_id: sessionId,
      saved_at: new Date().toISOString(),
      state,
      locked_parameters: Array.from(lockedParameters),
      analysis_result: analysisResult,
      full_setup: fullSetup,
    };
    try {
      saveSessionSnapshot(snapshot);
      saveLastLockedParameters(Array.from(lockedParameters));
      setSessionState(sessionId, state);
      setSessionStatesLocal((prev) => ({ ...prev, [sessionId]: state }));
      setSavedSnapshots((prev) => ({ ...prev, [sessionId]: getSessionSnapshot(sessionId) }));
      setSavedId(sessionId);
      setTimeout(() => setSavedId((current) => (current === sessionId ? null : current)), 2000);
    } catch (error: unknown) {
      const message = error instanceof Error
        ? error.message
        : 'No se pudo guardar el estado local de la sesion';
      setActionError(message);
    }
  }, [activeSessionId, hasLoadedData, analysisResult, lockedParameters, fullSetup]);

  // ── Load a session's files from the server ──
  const handleLoad = useCallback(async (item: SessionInfo) => {
    setLoadingId(item.id);
    setLoadedId(null);
    setActionError(null);

    try {
      const saved = getSessionSnapshot(item.id);
      const [telemetry, setup] = await Promise.all([
        loadSessionTelemetry(item.id),
        getSetup(item.id),
      ]);

      setActiveSessionId(item.id);
      if (saved?.analysis_result) {
        setAnalysisResult({
          ...telemetry,
          ...saved.analysis_result,
          // Keep telemetry/map series from backend to avoid stale or oversized local snapshots.
          circuit_data: telemetry.circuit_data,
          issues_on_map: telemetry.issues_on_map,
          laps_data: telemetry.laps_data,
          telemetry_series: telemetry.telemetry_series,
        });
      } else {
        setAnalysisResult(telemetry);
      }
      if (saved?.full_setup) {
        setFullSetup(saved.full_setup);
      } else {
        setFullSetup(setup);
      }
      setLockedParameters(new Set(saved?.locked_parameters ?? []));
      const prevState = sessionStates[item.id];
      if (!prevState || prevState === 'uploaded') {
        setSessionState(item.id, 'telemetry_loaded');
        setSessionStatesLocal((prev) => ({ ...prev, [item.id]: 'telemetry_loaded' }));
      }
      setLoadedId(item.id);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'No se pudo cargar la sesion';
      setActionError(message);
    } finally {
      setLoadingId(null);
    }
  }, [setActiveSessionId, setAnalysisResult, setFullSetup, setLockedParameters, sessionStates]);

  // ── Delete a whole server session ──
  const handleDelete = useCallback(async (item: SessionInfo) => {
    try {
      await deleteSession(item.id);
      removeSessionState(item.id);
      removeSessionSnapshot(item.id);
      setSavedSnapshots((prev) => {
        const next = { ...prev };
        delete next[item.id];
        return next;
      });
      if (activeSessionId === item.id) {
        setActiveSessionId(null);
        setAnalysisResult(null);
        setAnalysisError(null);
        setFullSetup(null);
        setLockedParameters(new Set());
        setLoadedId(null);
      }
      refresh();
    } catch {
      // ignore
    }
  }, [activeSessionId, setActiveSessionId, setAnalysisResult, setAnalysisError, setFullSetup, setLockedParameters, refresh]);

  const handleCleanup = useCallback(async () => {
    await cleanup();
    clearAllSessionStates();
    clearAllSessionSnapshots();
    setSessionStatesLocal({});
    setSavedSnapshots({});
    refresh();
  }, [refresh]);

  const renderItem = ({ item: session }: { item: SessionInfo }) => {
    const state = sessionStates[session.id];
    const isLoadingThis = loadingId === session.id;
    const isLoadedThis = activeSessionId === session.id || loadedId === session.id;
    const saved = savedSnapshots[session.id] ?? null;
    const canSaveThis = isLoadedThis && hasLoadedData;

    return (
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.sessionName} numberOfLines={1}>{telemetryName(session.telemetry)}</Text>
          {state && (
            <View style={[styles.stateBadge, { backgroundColor: STATE_COLORS[state] + '22', borderColor: STATE_COLORS[state] }]}>
              <Text style={[styles.stateBadgeText, { color: STATE_COLORS[state] }]}>
                {STATE_LABELS[state]}
              </Text>
            </View>
          )}
        </View>
        <Text style={styles.fileInfo}>Telemetria: {session.telemetry}</Text>
        <Text style={styles.fileInfo}>Setup: {session.svm}</Text>

        <View style={styles.cardActions}>
          <Pressable
            style={[styles.actionBtn, styles.loadBtn, isLoadingThis && styles.actionBtnDisabled]}
            onPress={() => handleLoad(session)}
            disabled={isLoadingThis}
          >
            {isLoadingThis ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={styles.actionBtnText}>{isLoadedThis ? 'Cargada ✓' : 'Cargar'}</Text>
            )}
          </Pressable>
          <Pressable
            style={[styles.actionBtn, styles.saveBtnInline, !canSaveThis && styles.actionBtnDisabled]}
            onPress={() => handleSave(session.id)}
            disabled={!canSaveThis}
          >
            <Text style={styles.actionBtnText}>{savedId === session.id ? 'Guardada ✓' : 'Guardar'}</Text>
          </Pressable>
          <Pressable
            style={[styles.actionBtn, styles.deleteBtn]}
            onPress={() => handleDelete(session)}
          >
            <Text style={styles.actionBtnText}>Eliminar</Text>
          </Pressable>
        </View>
        {saved ? (
          <Text style={styles.snapshotInfo}>
            Estado guardado: {new Date(saved.saved_at).toLocaleString('es-ES')}
          </Text>
        ) : null}
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Sesiones</Text>
        <View style={styles.headerActions}>
          <Pressable style={styles.cleanBtn} onPress={handleCleanup}>
            <Text style={styles.cleanText}>Limpiar todo</Text>
          </Pressable>
        </View>
      </View>

      {loading ? (
        <ActivityIndicator size="large" color="#e53935" />
      ) : sessions.length === 0 ? (
        <View>
          <Text style={styles.empty}>No hay sesiones. Sube archivos primero.</Text>
          {actionError ? <Text style={styles.error}>{actionError}</Text> : null}
        </View>
      ) : (
        <>
          {actionError ? <Text style={styles.error}>{actionError}</Text> : null}
          <FlatList
            data={sessions}
            keyExtractor={(entry) => `session::${entry.id}`}
            renderItem={renderItem}
            contentContainerStyle={{ paddingBottom: 24 }}
          />
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
    padding: 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
    flexWrap: 'wrap',
    gap: 8,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
  },
  headerActions: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  cleanBtn: {
    backgroundColor: '#333',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 6,
  },
  cleanText: {
    color: '#f44336',
    fontWeight: '600',
  },
  card: {
    backgroundColor: '#1a1a3e',
    padding: 16,
    borderRadius: 8,
    marginBottom: 12,
  },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 6,
    gap: 8,
  },
  sessionName: {
    color: '#fff',
    fontWeight: 'bold',
    flex: 1,
    fontSize: 14,
  },
  stateBadge: {
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 8,
    paddingVertical: 2,
  },
  stateBadgeText: {
    fontSize: 11,
    fontWeight: '600',
  },
  fileInfo: {
    color: '#888',
    fontSize: 12,
    marginBottom: 2,
  },
  snapshotInfo: {
    color: '#4caf50',
    fontSize: 12,
    marginTop: 4,
  },
  cardActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 10,
    minHeight: 40,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
  },
  loadBtn: {
    backgroundColor: '#1565c0',
  },
  saveBtnInline: {
    backgroundColor: '#2e7d32',
  },
  deleteBtn: {
    backgroundColor: '#7f1515',
  },
  actionBtnDisabled: {
    opacity: 0.5,
  },
  actionBtnText: {
    color: '#fff',
    fontWeight: '600',
    fontSize: 13,
  },
  empty: {
    color: '#666',
    textAlign: 'center',
    marginTop: 48,
    fontSize: 15,
  },
  error: {
    color: '#f44336',
    textAlign: 'center',
    marginTop: 8,
    fontSize: 13,
  },
});
