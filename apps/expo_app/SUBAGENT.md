# SUBAGENT.md - Expo App

Subagente especializado en app Expo (React Native Web).

## Loop

1. Recibir tarea.
2. Crear worktree obligatorio.
3. Implementar alcance exacto.
4. Ejecutar gates Expo.
5. Commit convencional.
6. Reportar al Supervisor y detener.

## Worktree obligatorio

```bash
git checkout develop
git pull
git worktree add .worktrees/expo-<task-slug> -b feature/<task-id>-<desc> develop
```

## Gates Expo

- `npx expo lint`
- `npx jest`
- `npx expo export -p web`
- E2E cuando la entrega impacta `develop` o `main`

## Restricciones

- Sin merges.
- Sin scope creep.
- Si hay dependencia faltante, bloquear y reportar.
