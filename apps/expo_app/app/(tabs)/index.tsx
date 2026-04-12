import { useEffect, useState, useCallback } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, Pressable, TextInput, ScrollView } from 'react-native';
import { healthCheck, authRegister, authVerify, authLogin } from '../../src/api';
import { useAppStore } from '../../src/store/useAppStore';

type AuthView = 'login' | 'register' | 'verify';

export default function HomeScreen() {
  const { serverStatus, setServerStatus, jwt, authUsername, setAuth, clearAuth, setOllamaApiKey, setSelectedModel } = useAppStore();
  const [loading, setLoading] = useState(true);
  const isLoggedIn = Boolean(jwt);

  // Auth form state
  const [authView, setAuthView] = useState<AuthView>('login');
  const [formUsername, setFormUsername] = useState('');
  const [formEmail, setFormEmail] = useState('');
  const [formPassword, setFormPassword] = useState('');
  const [formConfirmEmail, setFormConfirmEmail] = useState('');
  const [formConfirmPassword, setFormConfirmPassword] = useState('');
  const [verifyCode, setVerifyCode] = useState('');
  const [verifyEmail, setVerifyEmail] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);
  const [authSuccess, setAuthSuccess] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(false);

  useEffect(() => {
    healthCheck()
      .then((res) => setServerStatus(res.status === 'ok' ? 'ok' : 'degraded'))
      .catch(() => setServerStatus('offline'))
      .finally(() => setLoading(false));
  }, [setServerStatus]);

  const handleLogin = useCallback(async () => {
    if (!formUsername.trim() || !formPassword.trim()) {
      setAuthError('Introduce usuario y contraseña');
      return;
    }
    setAuthLoading(true);
    setAuthError(null);
    setAuthSuccess(null);
    try {
      const res = await authLogin(formUsername.trim(), formPassword);
      setAuth(res.token, res.username, res.is_admin);
      if (res.ollama_api_key) setOllamaApiKey(res.ollama_api_key);
      if (res.ollama_model) setSelectedModel(res.ollama_model);
      setFormPassword('');
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Error al iniciar sesión';
      // Try to extract API error message
      if (typeof e === 'object' && e !== null && 'response' in e) {
        const axiosErr = e as { response?: { data?: { error?: string } } };
        setAuthError(axiosErr.response?.data?.error ?? msg);
      } else {
        setAuthError(msg);
      }
    } finally {
      setAuthLoading(false);
    }
  }, [formUsername, formPassword, setAuth, setOllamaApiKey, setSelectedModel]);

  const handleRegister = useCallback(async () => {
    if (!formUsername.trim() || !formEmail.trim() || !formPassword.trim() || !formConfirmEmail.trim() || !formConfirmPassword.trim()) {
      setAuthError('Completa todos los campos');
      return;
    }
    if (formEmail.trim().toLowerCase() !== formConfirmEmail.trim().toLowerCase()) {
      setAuthError('Los emails no coinciden');
      return;
    }
    if (formPassword !== formConfirmPassword) {
      setAuthError('Las contraseñas no coinciden');
      return;
    }
    if (formPassword.length < 8) {
      setAuthError('La contraseña debe tener al menos 8 caracteres');
      return;
    }
    setAuthLoading(true);
    setAuthError(null);
    setAuthSuccess(null);
    try {
      const res = await authRegister(formUsername.trim(), formEmail.trim(), formPassword);
      setVerifyEmail(formEmail.trim());
      setFormPassword('');
      if (res.code) {
        // Dev mode (SMTP not configured): code returned in response — auto-fill it
        setVerifyCode(res.code);
        setAuthSuccess(`Código de verificación: ${res.code} (rellenado automáticamente)`);
      } else {
        setAuthSuccess('Registro exitoso. Revisa tu email para el código de verificación.');
      }
      setAuthView('verify');
    } catch (e: unknown) {
      if (typeof e === 'object' && e !== null && 'response' in e) {
        const axiosErr = e as { response?: { data?: { error?: string } } };
        setAuthError(axiosErr.response?.data?.error ?? 'Error al registrar');
      } else {
        setAuthError(e instanceof Error ? e.message : 'Error al registrar');
      }
    } finally {
      setAuthLoading(false);
    }
  }, [formUsername, formEmail, formPassword, formConfirmEmail, formConfirmPassword]);

  const handleVerify = useCallback(async () => {
    if (!verifyCode.trim()) {
      setAuthError('Introduce el código de verificación');
      return;
    }
    setAuthLoading(true);
    setAuthError(null);
    setAuthSuccess(null);
    try {
      await authVerify(verifyEmail, verifyCode.trim());
      setAuthSuccess('Email verificado. Ya puedes iniciar sesión.');
      setAuthView('login');
      setVerifyCode('');
    } catch (e: unknown) {
      if (typeof e === 'object' && e !== null && 'response' in e) {
        const axiosErr = e as { response?: { data?: { error?: string } } };
        setAuthError(axiosErr.response?.data?.error ?? 'Error al verificar');
      } else {
        setAuthError(e instanceof Error ? e.message : 'Error al verificar');
      }
    } finally {
      setAuthLoading(false);
    }
  }, [verifyEmail, verifyCode]);

  const handleLogout = useCallback(() => {
    clearAuth();
    setFormUsername('');
    setFormPassword('');
    setAuthError(null);
    setAuthSuccess(null);
  }, [clearAuth]);

  return (
    <ScrollView style={styles.scrollContainer} contentContainerStyle={styles.container}>
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

      {isLoggedIn ? (
        /* ── Logged-in view ── */
        <View style={styles.card}>
          <Text style={styles.welcomeText}>Bienvenido, {authUsername}</Text>
          <Text style={styles.instructions}>
            1. Ve a la pestaña "Datos" para cargar tus archivos de telemetría (.ld) y setup (.svm){'\n'}
            2. Inicia el análisis en la pestaña "Análisis"{'\n'}
            3. Revisa los resultados: mapa del circuito, análisis de conducción y recomendaciones de setup
          </Text>
          <Pressable style={styles.logoutBtn} onPress={handleLogout}>
            <Text style={styles.btnText}>Cerrar Sesión</Text>
          </Pressable>
        </View>
      ) : (
        /* ── Auth forms ── */
        <View style={styles.card}>
          {authView === 'login' && (
            <>
              <Text style={styles.cardTitle}>Iniciar Sesión</Text>
              <TextInput
                style={styles.input}
                placeholder="Usuario"
                placeholderTextColor="#777"
                value={formUsername}
                onChangeText={setFormUsername}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <TextInput
                style={styles.input}
                placeholder="Contraseña"
                placeholderTextColor="#777"
                value={formPassword}
                onChangeText={setFormPassword}
                secureTextEntry
                onSubmitEditing={handleLogin}
                returnKeyType="go"
              />
              <Pressable
                style={[styles.primaryBtn, authLoading && styles.disabled]}
                onPress={handleLogin}
                disabled={authLoading}
              >
                {authLoading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Entrar</Text>}
              </Pressable>
              <Pressable onPress={() => { setAuthView('register'); setAuthError(null); setAuthSuccess(null); }}>
                <Text style={styles.linkText}>¿No tienes cuenta? Regístrate</Text>
              </Pressable>
            </>
          )}

          {authView === 'register' && (
            <>
              <Text style={styles.cardTitle}>Registro</Text>
              <TextInput
                style={styles.input}
                placeholder="Usuario (mín. 3 caracteres)"
                placeholderTextColor="#777"
                value={formUsername}
                onChangeText={setFormUsername}
                autoCapitalize="none"
                autoCorrect={false}
              />
              <TextInput
                style={styles.input}
                placeholder="Email"
                placeholderTextColor="#777"
                value={formEmail}
                onChangeText={setFormEmail}
                autoCapitalize="none"
                keyboardType="email-address"
              />
              <TextInput
                style={styles.input}
                placeholder="Confirmar email"
                placeholderTextColor="#777"
                value={formConfirmEmail}
                onChangeText={setFormConfirmEmail}
                autoCapitalize="none"
                keyboardType="email-address"
              />
              <TextInput
                style={styles.input}
                placeholder="Contraseña (mín. 8 caracteres)"
                placeholderTextColor="#777"
                value={formPassword}
                onChangeText={setFormPassword}
                secureTextEntry
              />
              <TextInput
                style={styles.input}
                placeholder="Confirmar contraseña"
                placeholderTextColor="#777"
                value={formConfirmPassword}
                onChangeText={setFormConfirmPassword}
                secureTextEntry
              />
              <Pressable
                style={[styles.primaryBtn, authLoading && styles.disabled]}
                onPress={handleRegister}
                disabled={authLoading}
              >
                {authLoading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Registrar</Text>}
              </Pressable>
              <Pressable onPress={() => { setAuthView('login'); setAuthError(null); setAuthSuccess(null); }}>
                <Text style={styles.linkText}>¿Ya tienes cuenta? Inicia sesión</Text>
              </Pressable>
            </>
          )}

          {authView === 'verify' && (
            <>
              <Text style={styles.cardTitle}>Verificar Email</Text>
              <Text style={styles.helperText}>Introduce el código enviado a {verifyEmail}</Text>
              <TextInput
                style={styles.input}
                placeholder="Código de 6 dígitos"
                placeholderTextColor="#777"
                value={verifyCode}
                onChangeText={setVerifyCode}
                keyboardType="number-pad"
                maxLength={6}
              />
              <Pressable
                style={[styles.primaryBtn, authLoading && styles.disabled]}
                onPress={handleVerify}
                disabled={authLoading}
              >
                {authLoading ? <ActivityIndicator color="#fff" /> : <Text style={styles.btnText}>Verificar</Text>}
              </Pressable>
              <Pressable onPress={() => { setAuthView('login'); setAuthError(null); setAuthSuccess(null); }}>
                <Text style={styles.linkText}>Volver a inicio de sesión</Text>
              </Pressable>
            </>
          )}

          {authError && <Text style={styles.error}>{authError}</Text>}
          {authSuccess && <Text style={styles.success}>{authSuccess}</Text>}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scrollContainer: {
    flex: 1,
    backgroundColor: '#0f0f23',
  },
  container: {
    padding: 24,
    alignItems: 'center',
    minHeight: '100%',
    justifyContent: 'center',
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
  card: {
    backgroundColor: '#1a1a3e',
    padding: 24,
    borderRadius: 12,
    width: '100%',
    maxWidth: 400,
    alignItems: 'stretch',
  },
  cardTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#fff',
    marginBottom: 16,
    textAlign: 'center',
  },
  welcomeText: {
    fontSize: 20,
    fontWeight: 'bold',
    color: '#4caf50',
    marginBottom: 16,
    textAlign: 'center',
  },
  input: {
    backgroundColor: '#0d0d1f',
    color: '#fff',
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: '#333',
    marginBottom: 12,
    fontSize: 15,
  },
  primaryBtn: {
    backgroundColor: '#e53935',
    paddingVertical: 14,
    borderRadius: 8,
    alignItems: 'center',
    marginBottom: 12,
  },
  logoutBtn: {
    backgroundColor: '#555',
    paddingVertical: 12,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 8,
  },
  disabled: {
    opacity: 0.4,
  },
  btnText: {
    color: '#fff',
    fontWeight: 'bold',
    fontSize: 15,
  },
  linkText: {
    color: '#64b5f6',
    textAlign: 'center',
    marginTop: 4,
    fontSize: 14,
  },
  helperText: {
    color: '#aaa',
    fontSize: 13,
    marginBottom: 12,
    textAlign: 'center',
  },
  instructions: {
    color: '#888',
    fontSize: 14,
    lineHeight: 22,
    textAlign: 'center',
    marginBottom: 16,
  },
  error: {
    color: '#f44336',
    fontSize: 13,
    marginTop: 8,
    textAlign: 'center',
  },
  success: {
    color: '#4caf50',
    fontSize: 13,
    marginTop: 8,
    textAlign: 'center',
  },
});
