import { Tabs } from 'expo-router';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: '#e53935',
        tabBarStyle: { backgroundColor: '#1a1a2e' },
        headerStyle: { backgroundColor: '#16213e' },
        headerTintColor: '#fff',
      }}
    >
      <Tabs.Screen
        name="index"
        options={{ title: 'Inicio', tabBarLabel: 'Inicio' }}
      />
      <Tabs.Screen
        name="upload"
        options={{ title: 'Subir Archivos', tabBarLabel: 'Upload' }}
      />
      <Tabs.Screen
        name="sessions"
        options={{ title: 'Sesiones', tabBarLabel: 'Sesiones' }}
      />
      <Tabs.Screen
        name="analysis"
        options={{ title: 'Análisis', tabBarLabel: 'Análisis' }}
      />
      <Tabs.Screen
        name="telemetry"
        options={{ title: 'Telemetría', tabBarLabel: 'Telemetría' }}
      />
      <Tabs.Screen
        name="tracks"
        options={{ title: 'Circuitos', tabBarLabel: 'Tracks' }}
      />
    </Tabs>
  );
}
