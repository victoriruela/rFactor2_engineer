import { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, ActivityIndicator } from 'react-native';
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
  type SessionInfo,
  type SessionState,
} from '../../src/api';

const STATE_LABELS: Record<SessionState, string> = {
  uploaded: 'Subido',
  telemetry_loaded: 'TelemetrÃ­a cargada',
  analysis_complete: 'AnÃ¡lisis completo',
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
  const { sessions, setSessions, setActiveSessionId, setAnalysisResult, setFullSetup } = useAppStore();
  const [loading, setLoading] = useState(true);
  const [sessionStates, setSessionStatesLocal] = useState<Record<string, SessionState>>({});
  const [loadingId, setLoadingId] = useState<string | null>(null);
  const [loadedId, setLoadedId] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSessions();
      setSessions(data);
      setSessionStatesLocal(getSessionStates());
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [setSessions]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleLoad = useCallback(async (item: SessionInfo) => {
    setLoadingId(item.id);
    setLoadedId(null);
    try {
      const [telemetry, setup] = await Promise.all([
        loadSessionTelemetry(item.id),
        getSetup(item.id),
      ]);
      setActiveSessionId(item.id);
      setAnalysisResult(telemetry);
      setFullSetup(setup);
      const prevState = sessionStates[item.id];
      if (!prevState || prevState === 'uploaded') {
        setSessionState(item.id, 'telemetry_loaded');
        setSessionStatesLocal((prev) => ({ ...prev, [item.id]: 'telemetry_loaded' }));
      }
      setLoadedId(item.id);
    } catch {
      // ignore
    } finally {
      setLoadingId(null);
    }
  }, [setActiveSessionId, setAnalysisResult, setFullSetup, sessionStates]);

  const handleDelete = useCallback(async (item: SessionInfo) => {
    try {
      await deleteSession(item.id);
      removeSessionState(item.id);
      refresh();
    } catch {
      // ignore
    }
  }, [refresh]);

  const handleCleanup = useCallback(async () => {
    await cleanup();
    clearAllSessionStates();
    setSessionStatesLocal({});
    refresh();
  }, [refresh]);

  const renderItem = ({ item }: { item: SessionInfo }) => {
    const state = sessionStates[item.id];
    const isLoadingThis = loadingId === item.id;
    const isLoadedThis = loadedId === item.id;
    return (
      <View style={styles.card}>
        <View style={styles.cardHeader}>
          <Text style={styles.sessionName} numberOfLines={1}>{telemetryName(item.telemetry)}</Text>
          {state && (
            <View style={[styles.stateBadge, { backgroundColor: STATE_COLORS[state] + '22', borderColor: STATE_COLORS[state] }]}>
              <Text style={[styles.stateBadgeText, { color: STATE_COLORS[state] }]}>
                {STATE_LABELS[state]}
              </Text>
            </View>
          )}
        </View>
        <Text style={styles.fileInfo}>TelemetrÃ­a: {item.telemetry}</Text>
        <Text style={styles.fileInfo}>Setup: {item.svm}</Text>
        <View style={styles.cardActions}>
          <Pressable
            style={[styles.actionBtn, styles.loadBtn, isLoadingThis && styles.actionBtnDisabled]}
            onPress={() => handleLoad(item)}
            disabled={isLoadingThis}
          >
            {isLoadingThis ? (
              <ActivityIndicator size="small" color="#fff" />
            ) : (
              <Text style={styles.actionBtnText}>{isLoadedThis ? 'âœ“ Cargado' : 'Cargar'}</Text>
            )}
          </Pressable>
          <Pressable
            style={[styles.actionBtn, styles.deleteBtn]}
            onPress={() => handleDelete(item)}
          >
            <Text style={styles.actionBtnText}>Eliminar</Text>
          </Pressable>
        </View>
      </View>
    );
  };

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Sesiones</Text>
        <Pressable style={styles.cleanBtn} onPress={handleCleanup}>
          <Text style={styles.cleanText}>Limpiar todo</Text>
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator size="large" color="#e53935" />
      ) : sessions.length === 0 ? (
        <Text style={styles.empty}>No hay sesiones. Sube archivos primero.</Text>
      ) : (
        <FlatList
          data={sessions}
          keyExtractor={(s) => s.id}
          renderItem={renderItem}
          contentContainerStyle={{ paddingBottom: 24 }}
        />
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
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
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
  cardActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 12,
  },
  actionBtn: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 6,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 36,
  },
  loadBtn: {
    backgroundColor: '#1565c0',
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
    fontSize: 14,
  },
});

