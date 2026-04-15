import { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  ScrollView,
  TextInput,
  ActivityIndicator,
  Modal,
  FlatList,
} from 'react-native';
import { useAppStore } from '../../src/store/useAppStore';
import {
  listModelRouting,
  saveModelRouting,
  authUpdateConfig,
  listAvailableModels,
} from '../../src/api';
import type { ModelInfo } from '../../src/api';

const AGENT_LABELS: Record<string, string> = {
  driving: 'Análisis de conducción',
  suspension: 'Ing. Suspensión',
  chassis: 'Ing. Chasis',
  aero: 'Ing. Aerodinámica',
  powertrain: 'Ing. Tren motriz',
  chief: 'Ingeniero jefe',
};

const ROLE_ORDER = ['driving', 'chief', 'aero', 'chassis', 'powertrain', 'suspension'];

// Benchmark defaults from the 36-model evaluation run
const DEFAULT_ROUTING: Record<string, { model: string; temperature: number }> = {
  driving: { model: 'kimi-k2:1t', temperature: 0.4 },
  chief: { model: 'kimi-k2:1t', temperature: 0.3 },
  aero: { model: 'gemma4:31b', temperature: 0.2 },
  chassis: { model: 'gemma4:31b', temperature: 0.2 },
  powertrain: { model: 'gemma3:12b', temperature: 0.2 },
  suspension: { model: 'cogito-2.1:671b', temperature: 0.2 },
};

const TEMP_STEP = 0.05;
const TEMP_MIN = 0.0;
const TEMP_MAX = 1.0;

function clampTemp(v: number): number {
  return Math.round(Math.max(TEMP_MIN, Math.min(TEMP_MAX, v)) / TEMP_STEP) * TEMP_STEP;
}

export default function ConfigScreen() {
  const { ollamaApiKey, setOllamaApiKey, jwt, isAdmin } = useAppStore();

  const [draftApiKey, setDraftApiKey] = useState(ollamaApiKey);
  const [assignments, setAssignments] = useState<Record<string, { model: string; temperature: number }>>({});
  const [fallback, setFallback] = useState('');

  const [availableModels, setAvailableModels] = useState<ModelInfo[]>([]);
  const [modelsLoading, setModelsLoading] = useState(false);
  const [modelsError, setModelsError] = useState<string | null>(null);

  const [pickerRole, setPickerRole] = useState<string | null>(null);
  const [restoreConfirmVisible, setRestoreConfirmVisible] = useState(false);

  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);

  // Sync draft API key when store changes (e.g., on login restore)
  useEffect(() => {
    setDraftApiKey(ollamaApiKey);
  }, [ollamaApiKey]);

  // Load routing on mount
  useEffect(() => {
    listModelRouting()
      .then((res) => {
        const asMap: Record<string, { model: string; temperature: number }> = {};
        for (const a of res.routing ?? []) {
          asMap[a.role] = { model: a.effective_model ?? a.model, temperature: a.temperature };
        }
        setAssignments(asMap);
        setFallback(res.fallback ?? '');
      })
      .catch(() => {
        // Seed with defaults if routing not yet configured
        setAssignments({ ...DEFAULT_ROUTING });
      });
  }, []);

  // Load available models from server (server uses its own configured credentials)
  const fetchAvailableModels = useCallback(() => {
    setModelsLoading(true);
    setModelsError(null);
    listAvailableModels()
      .then((m) => setAvailableModels(m))
      .catch((e: unknown) => {
        const msg = e instanceof Error ? e.message : 'Error al cargar modelos';
        setModelsError(msg);
      })
      .finally(() => setModelsLoading(false));
  }, []);

  useEffect(() => {
    fetchAvailableModels();
  }, [fetchAvailableModels]);

  const updateAssignment = useCallback((role: string, patch: Partial<{ model: string; temperature: number }>) => {
    setAssignments((prev) => ({
      ...prev,
      [role]: { ...prev[role], ...patch },
    }));
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSavedMsg(null);
    const apiKey = draftApiKey.trim();
    setOllamaApiKey(apiKey);
    try {
      const saves: Promise<unknown>[] = [authUpdateConfig(apiKey, '')];
      if (isAdmin) saves.push(saveModelRouting(assignments));
      await Promise.all(saves);
      setSavedMsg('Configuración guardada ✓');
      setTimeout(() => setSavedMsg(null), 3000);
    } catch {
      setSavedMsg('Error al guardar');
      setTimeout(() => setSavedMsg(null), 3000);
    } finally {
      setSaving(false);
    }
  }, [draftApiKey, assignments, setOllamaApiKey, isAdmin]);

  const executeRestore = useCallback(async () => {
    setAssignments({ ...DEFAULT_ROUTING });
    setSaving(true);
    setSavedMsg(null);
    try {
      await saveModelRouting(DEFAULT_ROUTING);
      setSavedMsg('Modelos restaurados ✓');
      setTimeout(() => setSavedMsg(null), 3000);
    } catch {
      setSavedMsg('Error al restaurar');
      setTimeout(() => setSavedMsg(null), 3000);
    } finally {
      setSaving(false);
    }
  }, []);

  const handleRestore = useCallback(() => {
    setRestoreConfirmVisible(true);
  }, []);

  const handlePickModel = useCallback((role: string, model: string) => {
    updateAssignment(role, { model });
    setPickerRole(null);
  }, [updateAssignment]);

  const pickerModels = availableModels.length > 0
    ? availableModels
    : Object.values(DEFAULT_ROUTING).map((a) => ({ name: a.model, size: 0 }));

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.title}>Configuración</Text>

      {/* API Key */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>API Key Ollama</Text>
        <TextInput
          style={styles.textInput}
          value={draftApiKey}
          onChangeText={setDraftApiKey}
          placeholder="sk-..."
          placeholderTextColor="#555"
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
        />
        <Text style={styles.hint}>La API key se envía en cada solicitud al servidor Ollama remoto.</Text>
      </View>

      {/* Model Routing — admin only */}
      {isAdmin && (
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>Asignación de Modelos por Rol</Text>
        {fallback ? <Text style={styles.hint}>Fallback global: {fallback}</Text> : null}

        {/* Available models status */}
        {modelsLoading && (
          <View style={styles.modelsStatusRow}>
            <ActivityIndicator size="small" color="#4a90e2" />
            <Text style={styles.hint}> Cargando modelos disponibles...</Text>
          </View>
        )}
        {modelsError && (
          <View style={styles.modelsStatusRow}>
            <Text style={styles.errorText}>{modelsError}</Text>
            <Pressable onPress={fetchAvailableModels} style={styles.retryBtn}>
              <Text style={styles.retryBtnText}>Reintentar</Text>
            </Pressable>
          </View>
        )}

        {/* Routing rows */}
        {ROLE_ORDER.map((role) => {
          const assignment = assignments[role];
          if (!assignment) return null;
          const temp = assignment.temperature;
          return (
            <View key={role} style={styles.routingRow}>
              <Text style={styles.routingRoleLabel}>{AGENT_LABELS[role] ?? role}</Text>

              {/* Model picker trigger */}
              <Pressable
                style={styles.modelBtn}
                onPress={() => setPickerRole(role)}
              >
                <Text style={styles.modelBtnText} numberOfLines={1}>
                  {assignment.model || '— seleccionar —'}
                </Text>
                <Text style={styles.modelBtnArrow}>▼</Text>
              </Pressable>

              {/* Temperature +/- control */}
              <View style={styles.tempControl}>
                <Pressable
                  style={styles.tempBtn}
                  onPress={() => updateAssignment(role, { temperature: clampTemp(temp - TEMP_STEP) })}
                >
                  <Text style={styles.tempBtnText}>−</Text>
                </Pressable>
                <Text style={styles.tempValue}>T={temp.toFixed(2)}</Text>
                <Pressable
                  style={styles.tempBtn}
                  onPress={() => updateAssignment(role, { temperature: clampTemp(temp + TEMP_STEP) })}
                >
                  <Text style={styles.tempBtnText}>+</Text>
                </Pressable>
              </View>
            </View>
          );
        })}
      </View>
      )}

      {/* Action buttons */}
      <View style={styles.actionRow}>
        <Pressable
          style={[styles.saveBtn, (saving || !jwt) && styles.disabled]}
          onPress={() => { void handleSave(); }}
          disabled={saving || !jwt}
        >
          {saving ? (
            <ActivityIndicator color="#fff" size="small" />
          ) : (
            <Text style={styles.saveBtnText}>
              {savedMsg ?? 'Guardar Config Ollama'}
            </Text>
          )}
        </Pressable>

        {isAdmin && (
        <Pressable
          style={[styles.restoreBtn, (saving || !jwt) && styles.disabled]}
          onPress={handleRestore}
          disabled={saving || !jwt}
        >
          <Text style={styles.restoreBtnText}>Restaurar modelos</Text>
        </Pressable>
        )}
      </View>

      {/* Model picker modal */}
      <Modal
        visible={pickerRole !== null}
        transparent
        animationType="fade"
        onRequestClose={() => setPickerRole(null)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalBox}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>
                {pickerRole ? (AGENT_LABELS[pickerRole] ?? pickerRole) : ''}
              </Text>
              <Pressable onPress={() => setPickerRole(null)} style={styles.modalCloseBtn}>
                <Text style={styles.modalCloseText}>✕</Text>
              </Pressable>
            </View>

            {modelsLoading ? (
              <ActivityIndicator color="#4a90e2" style={{ marginVertical: 24 }} />
            ) : (
              <FlatList
                data={pickerModels}
                keyExtractor={(item) => item.name}
                style={styles.modelList}
                renderItem={({ item }) => {
                  const isSelected = pickerRole !== null && assignments[pickerRole]?.model === item.name;
                  const isDefault = pickerRole !== null && DEFAULT_ROUTING[pickerRole]?.model === item.name;
                  return (
                    <Pressable
                      style={[styles.modelListItem, isSelected && styles.modelListItemSelected]}
                      onPress={() => pickerRole && handlePickModel(pickerRole, item.name)}
                    >
                      <Text style={[styles.modelListItemText, isSelected && styles.modelListItemTextSelected]}>
                        {isSelected ? '● ' : '  '}{item.name}
                        {isDefault ? ' ★' : ''}
                      </Text>
                    </Pressable>
                  );
                }}
              />
            )}
          </View>
        </View>
      </Modal>

      {/* Restore confirmation modal (works on web and native) */}
      <Modal
        visible={restoreConfirmVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setRestoreConfirmVisible(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.modalBox}>
            <Text style={styles.modalTitle}>Restaurar modelos</Text>
            <Text style={styles.confirmText}>
              ¿Restaurar la configuración de modelos a los valores óptimos del benchmark?
            </Text>
            <View style={styles.confirmActions}>
              <Pressable
                style={styles.confirmCancelBtn}
                onPress={() => setRestoreConfirmVisible(false)}
              >
                <Text style={styles.confirmCancelText}>Cancelar</Text>
              </Pressable>
              <Pressable
                style={styles.confirmRestoreBtn}
                onPress={() => {
                  setRestoreConfirmVisible(false);
                  void executeRestore();
                }}
              >
                <Text style={styles.confirmRestoreText}>Restaurar</Text>
              </Pressable>
            </View>
          </View>
        </View>
      </Modal>
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
  section: {
    width: '100%',
    marginBottom: 28,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
    marginBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
    paddingBottom: 6,
  },
  textInput: {
    borderWidth: 1,
    borderColor: '#333',
    backgroundColor: '#1a1a3e',
    color: '#fff',
    borderRadius: 8,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 14,
    marginBottom: 6,
  },
  hint: {
    color: '#666',
    fontSize: 12,
    marginBottom: 4,
  },
  modelsStatusRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 8,
    gap: 8,
  },
  errorText: {
    color: '#f44336',
    fontSize: 12,
    flex: 1,
  },
  retryBtn: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 4,
    borderWidth: 1,
    borderColor: '#555',
  },
  retryBtnText: {
    color: '#ccc',
    fontSize: 12,
  },
  routingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 10,
    borderBottomWidth: 1,
    borderBottomColor: '#1e1e3e',
    gap: 8,
    flexWrap: 'wrap',
  },
  routingRoleLabel: {
    color: '#ccc',
    fontSize: 13,
    fontWeight: '600',
    flex: 2,
    minWidth: 140,
  },
  modelBtn: {
    flex: 3,
    minWidth: 160,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#1a1a3e',
    borderWidth: 1,
    borderColor: '#333',
    borderRadius: 6,
    paddingHorizontal: 10,
    paddingVertical: 7,
  },
  modelBtnText: {
    color: '#4a90e2',
    fontSize: 12,
    flex: 1,
  },
  modelBtnArrow: {
    color: '#555',
    fontSize: 10,
    marginLeft: 4,
  },
  tempControl: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  tempBtn: {
    width: 28,
    height: 28,
    borderRadius: 4,
    backgroundColor: '#1a1a3e',
    borderWidth: 1,
    borderColor: '#333',
    alignItems: 'center',
    justifyContent: 'center',
  },
  tempBtnText: {
    color: '#ccc',
    fontSize: 16,
    fontWeight: 'bold',
    lineHeight: 18,
  },
  tempValue: {
    color: '#ff9800',
    fontSize: 12,
    fontWeight: '600',
    minWidth: 52,
    textAlign: 'center',
  },
  actionRow: {
    flexDirection: 'row',
    gap: 12,
    flexWrap: 'wrap',
    marginBottom: 32,
  },
  saveBtn: {
    backgroundColor: '#e53935',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
    alignItems: 'center',
    minWidth: 200,
  },
  saveBtnText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 14,
  },
  restoreBtn: {
    backgroundColor: '#1a1a3e',
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#555',
    alignItems: 'center',
  },
  restoreBtnText: {
    color: '#ccc',
    fontWeight: '600',
    fontSize: 14,
  },
  disabled: {
    opacity: 0.4,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.75)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  modalBox: {
    backgroundColor: '#12122a',
    borderRadius: 12,
    padding: 20,
    width: '100%',
    maxWidth: 480,
    maxHeight: '80%',
    borderWidth: 1,
    borderColor: '#333',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  modalTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    flex: 1,
  },
  modalCloseBtn: {
    padding: 4,
  },
  modalCloseText: {
    color: '#888',
    fontSize: 18,
  },
  modelList: {
    maxHeight: 400,
  },
  modelListItem: {
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 6,
    marginBottom: 4,
  },
  modelListItemSelected: {
    backgroundColor: '#1a2a4e',
    borderWidth: 1,
    borderColor: '#4a90e2',
  },
  modelListItemText: {
    color: '#ccc',
    fontSize: 13,
    fontFamily: 'monospace',
  },
  modelListItemTextSelected: {
    color: '#4a90e2',
    fontWeight: '600',
  },
  confirmText: {
    color: '#ccc',
    fontSize: 14,
    lineHeight: 20,
    marginTop: 8,
  },
  confirmActions: {
    marginTop: 20,
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
  },
  confirmCancelBtn: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#555',
    backgroundColor: '#1a1a3e',
  },
  confirmCancelText: {
    color: '#ccc',
    fontWeight: '600',
  },
  confirmRestoreBtn: {
    paddingVertical: 10,
    paddingHorizontal: 14,
    borderRadius: 8,
    backgroundColor: '#e53935',
  },
  confirmRestoreText: {
    color: '#fff',
    fontWeight: '700',
  },
});
