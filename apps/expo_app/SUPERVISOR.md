# SUPERVISOR.md - Expo App

Supervisor de tareas del dominio Expo.

## Responsabilidades

1. Desglosar tareas de UI, estado, API client y testing.
2. Asignar subagentes en paralelo cuando no haya dependencias.
3. Exigir worktree por tarea.
4. Integrar en `develop` tras gates verdes.

## Reglas de Integracion

- Ramas `feature/*` y `fix/*`: solo a `develop`.
- Promocion a `main`: solo desde `develop` o `hotfix/*`.
- E2E obligatorio al empujar `develop` o `main`.

## Worktrees (obligatorio)

```bash
git checkout develop
git pull
git worktree add .worktrees/expo-<task-slug> -b feature/<task-id>-<desc> develop
```

## Definition of Done

1. `npx expo lint` pasa.
2. `npx jest` pasa.
3. `npx expo export -p web` genera build limpio.
4. E2E pasa (si target es `develop` o `main`).
