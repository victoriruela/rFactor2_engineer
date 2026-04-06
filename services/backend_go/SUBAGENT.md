# SUBAGENT.md - Backend Go

Subagente especializado en backend Go.

## Loop

1. Recibir tarea.
2. Crear worktree obligatorio.
3. Implementar alcance exacto.
4. Ejecutar gates Go.
5. Commit convencional.
6. Reportar al Supervisor y detener.

## Worktree obligatorio

```bash
git checkout develop
git pull
git worktree add .worktrees/go-<task-slug> -b feature/<task-id>-<desc> develop
```

## Gates Go

- `go vet ./...`
- `go test ./...`
- `go build ./...`
- `go test ./e2e/...` para pushes a `develop` o `main`

## Restricciones

- Sin merges.
- Sin scope creep.
- Si hay dependencia faltante, bloquear y reportar.
