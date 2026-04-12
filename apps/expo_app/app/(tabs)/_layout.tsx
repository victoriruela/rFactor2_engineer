import { Tabs } from 'expo-router';
import { useAppStore } from '../../src/store/useAppStore';

export default function TabLayout() {
  const jwt = useAppStore((s) => s.jwt);
  const isLoggedIn = Boolean(jwt);

  return (
    <Tabs
      screenOptions={{
        lazy: true,
        tabBarActiveTintColor: '#e53935',
        tabBarStyle: { backgroundColor: '#1a1a2e' },
        headerStyle: { backgroundColor: '#16213e' },
        headerTintColor: '#fff',
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Inicio', tabBarLabel: 'Inicio' }} />
      <Tabs.Screen name="upload" options={{ title: 'Datos', tabBarLabel: 'Datos', href: isLoggedIn ? undefined : null }} />
      <Tabs.Screen name="analysis" options={{ title: 'Análisis', tabBarLabel: 'Análisis', href: isLoggedIn ? undefined : null }} />
      <Tabs.Screen name="telemetry" options={{ title: 'Telemetría', tabBarLabel: 'Telemetría', href: isLoggedIn ? undefined : null }} />
      <Tabs.Screen name="tracks" options={{ title: 'Circuitos', tabBarLabel: 'Circuitos', href: isLoggedIn ? undefined : null }} />
    </Tabs>
  );
}
