import { useEffect, useState } from 'react';
import { View, Text, StyleSheet, ActivityIndicator } from 'react-native';
import { healthCheck } from '../../src/api';
import { useAppStore } from '../../src/store/useAppStore';

export default function HomeScreen() {
  const { serverStatus, setServerStatus } = useAppStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    healthCheck()
      .then((res) => setServerStatus(res.status === 'ok' ? 'ok' : 'degraded'))
      .catch(() => setServerStatus('offline'))
      .finally(() => setLoading(false));
  }, [setServerStatus]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>rFactor2 Engineer</Text>
      <Text style={styles.subtitle}>Análisis de telemetría y setup con IA</Text>

      {loading ? (
        <ActivityIndicator size="large" color="#e53935" style={{ marginTop: 32 }} />
      ) : (
        <View style={styles.statusRow}>
          <View
            style={[
              styles.dot,
              {
                backgroundColor:
                  serverStatus === 'ok'
                    ? '#4caf50'
                    : serverStatus === 'degraded'
                    ? '#ff9800'
                    : '#f44336',
              },
            ]}
          />
          <Text style={styles.statusText}>
            Servidor:{' '}
            {serverStatus === 'ok'
              ? 'Conectado'
              : serverStatus === 'degraded'
              ? 'Degradado (Ollama no disponible)'
              : 'Sin conexión'}
          </Text>
        </View>
      )}

      <Text style={styles.instructions}>
        1. Ve a la pestaña "Subida" para subir tus archivos de telemetría (.mat/.csv) y setup (.svm){'\n'}
        2. Inicia el análisis en la pestaña "Análisis"{'\n'}
        3. Revisa los resultados: mapa del circuito, análisis de conducción y recomendaciones de setup
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
    padding: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  title: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: '#aaa',
    marginBottom: 32,
  },
  statusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 24,
  },
  dot: {
    width: 12,
    height: 12,
    borderRadius: 6,
    marginRight: 8,
  },
  statusText: {
    color: '#ccc',
    fontSize: 14,
  },
  instructions: {
    color: '#888',
    fontSize: 14,
    lineHeight: 22,
    textAlign: 'center',
    maxWidth: 500,
  },
});
