# AGENTS.md — Expo App

Guía operativa para agentes en `apps/expo_app/`.

## Dominio

Cliente Expo (React Native Web): visualización de telemetría y setup de rFactor 2,
circuit map interactivo, tabla de recomendaciones de setup, upload de archivos.

Stack: Expo SDK 52+ · React Native Web · TypeScript · React Navigation · axios · Zustand

## Quality Gates Expo

```bash
npx expo lint                           # lint + typecheck
npx jest                                # unit tests
npx expo export -p web                  # build dry-run (genera dist/)
npx maestro test e2e/                   # E2E (obligatorio en develop/main)
```

## Estructura

```
apps/expo_app/
├── src/
│   ├── api/
│   ├── screens/
│   ├── components/
│   ├── store/
│   └── navigation/
├── __tests__/
├── e2e/
├── app.config.ts
└── package.json
```

## Supervisor-Subagent

Aplicar `SUPERVISOR.md` y `SUBAGENT.md` en esta carpeta.

### Worktree Expo

```bash
git checkout develop && git pull
git worktree add .worktrees/expo-<task-slug> -b feature/<task-id>-expo-<desc> develop
```

## Asana MCP — Tareas Expo

Plantilla de notes (DoD incluido): `docs/asana-workflow.md:"## Plantilla DoD — Expo"`
Ciclo de vida completo (TODO→IN PROGRESS→ON HOLD→DONE): `docs/asana-workflow.md:"## Ciclo de Vida"`
