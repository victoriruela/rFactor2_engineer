import React, { useEffect } from 'react';
import { Stack } from 'expo-router';
import { View, Text, ScrollView, StyleSheet, Pressable } from 'react-native';
import { useAppStore } from '../src/store/useAppStore';
import { deleteSessionOnUnload } from '../src/api/client';

const TEXT_NODE_DEBUG_ENABLED =
  __DEV__ &&
  typeof window !== 'undefined' &&
  typeof window.localStorage !== 'undefined' &&
  window.localStorage.getItem('rf2_debug_text_nodes') === '1';

// DEV ONLY: Capture "Unexpected text node" errors from react-native-web View.
// Stores the JS stack trace so RootLayout can display it as an in-app overlay
// (no browser DevTools needed to identify the culprit component).
let _capturedTextNodeStacks: string[] = [];
let _textNodeOverlayUpdater: ((stacks: string[]) => void) | null = null;

if (TEXT_NODE_DEBUG_ENABLED) {
  const _origConsoleError = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    const msg = typeof args[0] === 'string' ? args[0] : '';
    if (msg.includes('Unexpected text node')) {
      // Capture JS call stack at this exact point — shows which component rendered the View
      const stack = new Error(msg).stack ?? msg;
      _capturedTextNodeStacks = [..._capturedTextNodeStacks, stack];
      // Notify the overlay component if mounted
      _textNodeOverlayUpdater?.([..._capturedTextNodeStacks]);
      // Also print to devtools for good measure
      _origConsoleError(...args);
      return;
    }
    _origConsoleError(...args);
  };
}

class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null; info: React.ErrorInfo | null }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { error: null, info: null };
  }
  override componentDidCatch(error: Error, info: React.ErrorInfo) {
    this.setState({ error, info });
  }
  override render() {
    if (this.state.error) {
      return (
        <ScrollView style={eb.container} contentContainerStyle={eb.content}>
          <Text style={eb.title}>ERROR CAPTURADO</Text>
          <Text style={eb.errorText}>{this.state.error.message}</Text>
          <Text style={eb.label}>Stack del error:</Text>
          <Text style={eb.mono}>{this.state.error.stack ?? '—'}</Text>
          <Text style={eb.label}>Component stack:</Text>
          <Text style={eb.mono}>{this.state.info?.componentStack ?? '—'}</Text>
        </ScrollView>
      );
    }
    return this.props.children;
  }
}

const eb = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#1a0000' },
  content: { padding: 20 },
  title: { color: '#ff5555', fontSize: 18, fontWeight: 'bold', marginBottom: 12 },
  errorText: { color: '#ffaaaa', fontSize: 14, marginBottom: 16 },
  label: { color: '#ff9900', fontSize: 12, fontWeight: 'bold', marginTop: 12, marginBottom: 4 },
  mono: { color: '#ccc', fontSize: 10, fontFamily: 'monospace', lineHeight: 16 },
});

/** DEV overlay: shows captured "text-node-in-View" stacks at the bottom of the screen */
function TextNodeDebugOverlay() {
  const [stacks, setStacks] = React.useState<string[]>(_capturedTextNodeStacks);
  const [dismissed, setDismissed] = React.useState(false);

  React.useEffect(() => {
    _textNodeOverlayUpdater = setStacks;
    return () => { _textNodeOverlayUpdater = null; };
  }, []);

  if (!__DEV__ || dismissed || stacks.length === 0) return null;

  return (
    <View style={[dbg.overlay, dbg.overlayPointerEvents]}>
      <ScrollView style={dbg.scroll} contentContainerStyle={dbg.content}>
        <View style={dbg.header}>
          <Text style={dbg.title}>[RF2-DEBUG] Unexpected text node in View ({stacks.length}x)</Text>
          <Pressable onPress={() => setDismissed(true)} style={dbg.close}>
            <Text style={dbg.closeText}>✕</Text>
          </Pressable>
        </View>
        {stacks.map((s, i) => (
          <Text key={i} style={dbg.stack}>{s}</Text>
        ))}
      </ScrollView>
    </View>
  );
}

const dbg = StyleSheet.create({
  overlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    maxHeight: 280,
    backgroundColor: 'rgba(0,0,30,0.97)',
    zIndex: 9999,
    borderTopWidth: 2,
    borderTopColor: '#f55',
  },
  overlayPointerEvents: {
    pointerEvents: 'box-none',
  },
  scroll: { flex: 1 },
  content: { padding: 10 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  title: { color: '#f55', fontSize: 11, fontWeight: 'bold', flex: 1 },
  close: { paddingHorizontal: 8, paddingVertical: 2 },
  closeText: { color: '#fff', fontSize: 14 },
  stack: { color: '#7cf', fontSize: 9, fontFamily: 'monospace', lineHeight: 14, marginBottom: 12 },
});

export default function RootLayout() {
  const activeSessionId = useAppStore((state) => state.activeSessionId);

  // Auto-cleanup session files when window closes (beforeunload with keepalive)
  useEffect(() => {
    const handleBeforeUnload = () => {
      if (activeSessionId && typeof window !== 'undefined') {
        // Use keepalive: true so fetch continues even after page unload
        deleteSessionOnUnload(activeSessionId);
      }
    };

    if (typeof window !== 'undefined') {
      window.addEventListener('beforeunload', handleBeforeUnload);
      return () => {
        window.removeEventListener('beforeunload', handleBeforeUnload);
      };
    }
  }, [activeSessionId]);

  return (
    <ErrorBoundary>
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
      </Stack>
      {TEXT_NODE_DEBUG_ENABLED ? <TextNodeDebugOverlay /> : null}
    </ErrorBoundary>
  );
}
