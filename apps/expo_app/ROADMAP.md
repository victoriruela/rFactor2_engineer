# ROADMAP - Expo App

Ver etiquetas de Stage en `AGENTS.md` (raíz).

---

## [STAGE-1-ENV] Fase 1 — Fundación del Cliente

### Tarea 1.1 — Inicializar app Expo y estructura modular
**Descripción**: Crear el proyecto Expo con TypeScript (`npx create-expo-app --template blank-typescript`).
Estructura por features (`src/screens/`, `src/components/`, `src/api/`, `src/store/`, `src/navigation/`).
Configurar React Navigation. Añadir dependencias base: `axios`, `zustand`, `react-native-svg`.
Variable de entorno `EXPO_PUBLIC_API_URL` para apuntar al backend Go.
**Archivos**: `apps/expo_app/app.config.ts`, `apps/expo_app/package.json`,
`apps/expo_app/src/navigation/AppNavigator.tsx`, `apps/expo_app/src/api/client.ts`
**Depende de**: ninguna

### Tarea 1.2 — Layout principal y navegación
**Descripción**: Implementar el shell de la app: barra de navegación con secciones
(Home, Sesiones, Upload, Análisis, Tracks). Pantalla de carga inicial con verificación
de conectividad al backend (`GET /api/health`).
**Archivos**: `src/screens/HomeScreen.tsx`, `src/navigation/AppNavigator.tsx`
**Depende de**: Tarea 1.1

---

## [STAGE-2-CORE] Fase 2 — Sesiones y Subida de Archivos

### Tarea 2.1 — Pantalla de sesiones
**Descripción**: Pantalla que muestre sesiones existentes (GET `/api/sessions`)
y permita seleccionar o crear una. Cada sesión muestra nombre de archivos y estado.
**Archivos**: `src/screens/SessionsScreen.tsx`, `src/api/sessions.ts`, `src/store/sessionStore.ts`
**Depende de**: Tarea 1.2

### Tarea 2.2 — Upload chunked con progreso
**Descripción**: Pantalla de subida. Usar file picker para selección de archivos .mat/.csv y .svm.
Upload chunked al backend (init/chunk/complete) con barra de progreso.
**Archivos**: `src/screens/UploadScreen.tsx`, `src/api/upload.ts`,
`src/components/UploadProgress.tsx`
**Depende de**: Tarea 2.1

---

## [STAGE-3-ANALYSIS] Fase 3 — Visualización de Análisis

### Tarea 3.1 — Pantalla de análisis
**Descripción**: Pantalla que muestre resultados del análisis de IA. Secciones:
- Circuit map SVG con puntos GPS coloreados (rojo=driving, amarillo=setup, naranja=ambos)
- Texto de análisis de conducción (5 puntos por curva)
- Tabla de setup con parámetro, valor actual, nuevo valor, % cambio, razón
Selector de modelo LLM. Botón de lanzar análisis.
**Archivos**: `src/screens/AnalysisScreen.tsx`, `src/api/analysis.ts`,
`src/components/CircuitMap.tsx`, `src/components/SetupTable.tsx`
**Depende de**: Tarea 2.2

### Tarea 3.2 — Track library
**Descripción**: Pantalla de biblioteca de tracks. Lista tracks disponibles (GET `/api/tracks`).
Visualización del trazado del circuito.
**Archivos**: `src/screens/TrackScreen.tsx`, `src/api/tracks.ts`
**Depende de**: Tarea 1.2

---

## [STAGE-4-QA] Fase 4 — Calidad y Tests

### Tarea 4.1 — Tests unitarios
**Descripción**: Jest tests para components (CircuitMap, SetupTable, UploadProgress) y
API layer (sessions, upload, analysis). Mock de axios.
**Archivos**: `__tests__/components/`, `__tests__/api/`
**Depende de**: Tarea 3.1

### Tarea 4.2 — Tests E2E con Maestro
**Descripción**: Flujo E2E: upload telemetría → esperar análisis → verificar tabla visible.
Requiere backend Go corriendo en localhost.
**Archivos**: `e2e/full_flow.yaml`
**Depende de**: Tarea 4.1

---

## [STAGE-5-RELEASE] Fase 5 — Build y Release

### Tarea 5.1 — Build web para embebido en Go
**Descripción**: Configurar `npx expo export -p web` para generar `dist/` limpio.
Este directorio se copia a `services/backend_go/internal/web/dist/` para ser embebido
con `go:embed` en el binario final.
**Archivos**: `scripts/build-expo-web.ps1`
**Depende de**: Tarea 4.2
