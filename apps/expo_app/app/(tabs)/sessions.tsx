import { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, ActivityIndicator } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import { listSessions, cleanup, type SessionInfo } from '../../src/api';

export default function SessionsScreen() {
  const { sessions, setSessions } = useAppStore();
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listSessions();
      setSessions(data);
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, [setSessions]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleCleanup = useCallback(async () => {
    await cleanup();
    refresh();
  }, [refresh]);

  const renderItem = ({ item }: { item: SessionInfo }) => (
    <View style={styles.card}>
      <Text style={styles.sessionId}>{item.id}</Text>
      <Text style={styles.fileInfo}>Telemetría: {item.telemetry}</Text>
      <Text style={styles.fileInfo}>Setup: {item.svm}</Text>
    </View>
  );

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
  sessionId: {
    color: '#fff',
    fontWeight: 'bold',
    marginBottom: 4,
  },
  fileInfo: {
    color: '#aaa',
    fontSize: 13,
  },
  empty: {
    color: '#666',
    textAlign: 'center',
    marginTop: 48,
    fontSize: 14,
  },
});
