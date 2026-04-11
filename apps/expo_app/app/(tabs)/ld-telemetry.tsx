/**
 * LdTelemetry screen — client-side MoTeC .ld file parser.
 *
 * Uses the WASM parser (Rust → WebAssembly) via a Web Worker.
 * All parsing is off the main thread. Files are never fully loaded into memory —
 * only the exact byte ranges needed are sliced from the File object.
 */
import { useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  ActivityIndicator,
  Platform,
} from 'react-native';
import { useLdFileDirect } from '../../src/hooks/useLdFileDirect';
import type { ChannelInfo } from '../../src/worker/worker-protocol';

// ---------------------------------------------------------------------------
// File picker (web only — uses the <input type="file"> API)
// ---------------------------------------------------------------------------

function useFilePicker(onFile: (file: File) => void) {
  const inputRef = useRef<HTMLInputElement | null>(null);

  const open = useCallback(() => {
    if (Platform.OS !== 'web') return;
    if (!inputRef.current) {
      const el = document.createElement('input');
      el.type = 'file';
      el.accept = '.ld';
      el.style.display = 'none';
      el.onchange = () => {
        const file = el.files?.[0];
        if (file) onFile(file);
        el.value = '';
      };
      document.body.appendChild(el);
      inputRef.current = el;
    }
    inputRef.current.click();
  }, [onFile]);

  return open;
}

// ---------------------------------------------------------------------------
// Channel list row
// ---------------------------------------------------------------------------

function ChannelRow({ ch }: { ch: ChannelInfo }) {
  return (
    <View style={styles.channelRow}>
      <View style={styles.channelLeft}>
        <Text style={styles.channelName}>{ch.name}</Text>
        {ch.shortName ? (
          <Text style={styles.channelShort}>{ch.shortName}</Text>
        ) : null}
      </View>
      <View style={styles.channelRight}>
        <Text style={styles.channelMeta}>
          {ch.sampleRate} Hz · {ch.count.toLocaleString()} muestras
        </Text>
        {ch.units ? (
          <Text style={styles.channelUnits}>{ch.units}</Text>
        ) : null}
      </View>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Main screen
// ---------------------------------------------------------------------------

export default function LdTelemetryScreen() {
  const { state, loadFile, reset } = useLdFileDirect();

  const openFile = useFilePicker(loadFile);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <View style={styles.root}>
      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.title}>Telemetría MoTeC .ld</Text>
        <Text style={styles.subtitle}>
          Parsing cliente — sin subida al servidor
        </Text>
      </View>

      {/* Action bar */}
      <View style={styles.actionBar}>
        <Pressable
          style={[
            styles.btn,
            (state.kind === 'validating' ||
              state.kind === 'parsing_header' ||
              state.kind === 'parsing_channels') && styles.btnDisabled,
          ]}
          onPress={openFile}
          disabled={
            state.kind === 'validating' ||
            state.kind === 'parsing_header' ||
            state.kind === 'parsing_channels'
          }
        >
          <Text style={styles.btnText}>Abrir archivo .ld</Text>
        </Pressable>

        {state.kind === 'error' && (
          <Pressable style={[styles.btn, styles.btnSecondary]} onPress={reset}>
            <Text style={styles.btnText}>Reiniciar</Text>
          </Pressable>
        )}
      </View>

      {/* Status / content */}
      <ScrollView style={styles.body} contentContainerStyle={styles.bodyInner}>
        {state.kind === 'idle' && (
          <Text style={styles.hint}>
            Selecciona un archivo .ld para analizar su telemetría localmente.
          </Text>
        )}

        {(state.kind === 'validating' ||
          state.kind === 'parsing_header' ||
          state.kind === 'parsing_channels') && (
          <View style={styles.loadingRow}>
            <ActivityIndicator color="#4fc3f7" size="small" />
            <Text style={styles.loadingText}>{PHASE_LABEL[state.kind]}</Text>
          </View>
        )}

        {state.kind === 'error' && (
          <View style={styles.errorBox}>
            <Text style={styles.errorTitle}>Error al parsear</Text>
            <Text style={styles.errorMsg}>{state.message}</Text>
          </View>
        )}

        {state.kind === 'ready' && (
          <>
            {/* Session metadata */}
            <View style={styles.sessionCard}>
              <SessionRow label="Archivo" value={state.file.name} />
              <SessionRow label="Tamaño" value={formatBytes(state.file.size)} />
              <SessionRow label="Versión LD" value={String(state.session.version)} />
              <SessionRow label="Sesión" value={state.session.session || '—'} />
              <SessionRow label="Circuito" value={state.session.venue || '—'} />
              <SessionRow label="Vehículo" value={state.session.vehicle || '—'} />
              <SessionRow label="Piloto" value={state.session.driver || '—'} />
              <SessionRow label="Fecha" value={state.session.date || '—'} />
              <SessionRow
                label="Canales"
                value={String(state.channels.length)}
              />
            </View>

            {/* Channel list */}
            <Text style={styles.sectionTitle}>
              Canales disponibles ({state.channels.length})
            </Text>
            {state.channels.map((ch, idx) => (
              <ChannelRow key={`${ch.name}-${idx}`} ch={ch} />
            ))}
          </>
        )}
      </ScrollView>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PHASE_LABEL: Record<string, string> = {
  validating: 'Validando archivo…',
  parsing_header: 'Leyendo cabecera…',
  parsing_channels: 'Leyendo canales…',
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function SessionRow({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.sessionRow}>
      <Text style={styles.sessionLabel}>{label}</Text>
      <Text style={styles.sessionValue}>{value}</Text>
    </View>
  );
}

// ---------------------------------------------------------------------------
// Styles
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#0a0a1a' },

  header: {
    paddingHorizontal: 16,
    paddingTop: 20,
    paddingBottom: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#1e3a5f',
  },
  title: { fontSize: 18, fontWeight: '700', color: '#e0e0e0' },
  subtitle: { fontSize: 12, color: '#607d8b', marginTop: 2 },

  actionBar: {
    flexDirection: 'row',
    gap: 10,
    padding: 12,
  },
  btn: {
    backgroundColor: '#1565c0',
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 6,
  },
  btnDisabled: { opacity: 0.5 },
  btnSecondary: { backgroundColor: '#37474f' },
  btnText: { color: '#fff', fontSize: 14, fontWeight: '600' },

  body: { flex: 1 },
  bodyInner: { padding: 16, paddingBottom: 80 },

  hint: { color: '#78909c', fontSize: 14, textAlign: 'center', marginTop: 40 },

  loadingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingVertical: 20,
  },
  loadingText: { color: '#90caf9', fontSize: 14 },

  errorBox: {
    backgroundColor: '#1a0000',
    borderWidth: 1,
    borderColor: '#c62828',
    borderRadius: 8,
    padding: 14,
    marginTop: 8,
  },
  errorTitle: { color: '#ef9a9a', fontWeight: '700', marginBottom: 4 },
  errorMsg: { color: '#ef5350', fontSize: 12, fontFamily: 'monospace' },

  sessionCard: {
    backgroundColor: '#0d1b2a',
    borderWidth: 1,
    borderColor: '#1e3a5f',
    borderRadius: 8,
    padding: 12,
    marginBottom: 20,
  },
  sessionRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 4,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#1e3a5f',
  },
  sessionLabel: { color: '#78909c', fontSize: 13 },
  sessionValue: { color: '#e0e0e0', fontSize: 13, fontWeight: '500', maxWidth: '65%', textAlign: 'right' },

  sectionTitle: {
    color: '#90caf9',
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 8,
  },

  channelRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#1e3a5f',
  },
  channelLeft: { flex: 1 },
  channelName: { color: '#e0e0e0', fontSize: 13, fontWeight: '500' },
  channelShort: { color: '#607d8b', fontSize: 11, marginTop: 2 },
  channelRight: { alignItems: 'flex-end', marginLeft: 12 },
  channelMeta: { color: '#78909c', fontSize: 11 },
  channelUnits: { color: '#4fc3f7', fontSize: 11, marginTop: 2 },
});
