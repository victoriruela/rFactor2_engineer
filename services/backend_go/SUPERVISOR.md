# SUPERVISOR.md - Backend Go

Supervisor de tareas del dominio backend Go.

## Responsabilidades

1. Partir trabajo en tareas de API, dominio, infra y tests.
2. Asignar subagentes en paralelo sin romper dependencias.
3. Exigir worktrees para todo subagente.
4. Integrar en `develop` tras gates verdes.

## Reglas de Integracion

- `feature/*` y `fix/*` solo a `develop`.
- `main` solo recibe `develop` y `hotfix/*`.
- Push a `develop` o `main` dispara E2E.

## Worktrees (obligatorio)

```bash
git checkout develop
git pull
git worktree add .worktrees/go-<task-slug> -b feature/<task-id>-<desc> develop
```

## Definition of Done

1. `go vet ./...` pasa.
2. `go test ./...` pasa.
3. `go build ./...` pasa.
4. E2E pasa (si target es `develop` o `main`).
