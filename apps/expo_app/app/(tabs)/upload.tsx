import { useState, useCallback } from 'react';
import { View, Text, StyleSheet, Pressable, ActivityIndicator, Platform } from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import { uploadFile } from '../../src/api';

export default function UploadScreen() {
  const {
    telemetryFile, svmFile,
    setTelemetryFile, setSvmFile,
    uploadProgress, setUploadProgress,
    isUploading, setUploading,
  } = useAppStore();
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

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

  const handleUpload = useCallback(async () => {
    if (!telemetryFile || !svmFile) {
      setError('Selecciona ambos archivos');
      return;
    }

    setUploading(true);
    setError(null);
    setSuccess(false);
    setUploadProgress(0);

    try {
      await uploadFile(telemetryFile, (pct) => setUploadProgress(pct / 2));
      await uploadFile(svmFile, (pct) => setUploadProgress(50 + pct / 2));
      setSuccess(true);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error de subida';
      setError(msg);
    } finally {
      setUploading(false);
    }
  }, [telemetryFile, svmFile, setUploading, setUploadProgress]);

  return (
    <View style={styles.container}>
      <Text style={styles.title}>Subir Archivos</Text>

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
          <Text style={styles.uploadText}>Subir Archivos</Text>
        </Pressable>
      )}

      {error && <Text style={styles.error}>{error}</Text>}
      {success && <Text style={styles.success}>Archivos subidos correctamente</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0f0f23',
    padding: 24,
    alignItems: 'center',
    justifyContent: 'center',
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 32,
  },
  pickBtn: {
    backgroundColor: '#1a1a3e',
    paddingVertical: 16,
    paddingHorizontal: 32,
    borderRadius: 8,
    marginBottom: 16,
    width: '100%',
    maxWidth: 400,
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
    paddingVertical: 14,
    paddingHorizontal: 48,
    borderRadius: 8,
    marginTop: 16,
  },
  disabled: {
    opacity: 0.4,
  },
  uploadText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 16,
  },
  progressContainer: {
    width: '100%',
    maxWidth: 400,
    height: 32,
    backgroundColor: '#1a1a3e',
    borderRadius: 8,
    marginTop: 16,
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
  error: {
    color: '#f44336',
    marginTop: 16,
  },
  success: {
    color: '#4caf50',
    marginTop: 16,
  },
});
