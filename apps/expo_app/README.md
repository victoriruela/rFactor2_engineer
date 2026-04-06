# README — Expo App

Frontend del rFactor2 Engineer. App Expo (React Native Web) para visualización de telemetría y setup.

## Requisitos

- Node.js 20+
- Expo CLI (`npx expo`)

## Desarrollo

```bash
cd apps/expo_app
npm install
npx expo start --web
```

## Build Web (para embebido en Go binary)

```bash
npx expo export -p web
# Genera dist/ → copiar a services/backend_go/internal/web/dist/
```

## Variables de Entorno

| Variable | Default | Descripción |
|----------|---------|-------------|
| `EXPO_PUBLIC_API_URL` | `http://localhost:8080` | URL del backend Go |

## Tests

```bash
npx jest               # Unit tests
npx maestro test e2e/  # E2E (requiere backend corriendo)
```
