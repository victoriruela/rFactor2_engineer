# AGENTS.md — Backend Go

Guía operativa para agentes en `services/backend_go/`.

## Dominio

Backend Go: API de telemetría y setup, pipeline LLM de 4 agentes (Translation→Driving→Specialists→Chief),
parsers de .mat/.csv/.svm, gestión de sesiones, tracks, y servicio de la web app Expo embebida via `go:embed`.

Stack: Go 1.23+ · Gin · zerolog · SQLite (modernc.org/sqlite) · Ollama HTTP client directo · `go:embed`

## Quality Gates Go

```bash
go vet ./...              # lint
go test ./...             # tests
go build ./...            # build
go test -run '^$' ./...   # compilation dry-run
go test ./e2e/...         # E2E (obligatorio en develop/main)
```

## Estructura

```
services/backend_go/
├── cmd/server/main.go
├── config/
│   ├── fixed_params.json
│   ├── param_mapping.json
│   └── jimmy_runtime_config.v1.json
├── internal/
│   ├── config/
│   ├── health/
│   ├── sessions/
│   ├── upload/
│   ├── telemetry/
│   ├── llm/
│   ├── analysis/
│   ├── tracks/
│   └── web/
├── testdata/
├── e2e/
├── go.mod
└── go.sum
```

## Supervisor-Subagent

Aplicar `SUPERVISOR.md` y `SUBAGENT.md` en esta carpeta.

### Worktree Go

```bash
git checkout develop && git pull
git worktree add .worktrees/go-<task-slug> -b feature/<task-id>-go-<desc> develop
```

## Asana MCP — Tareas Go

Plantilla de notes (DoD incluido): `docs/asana-workflow.md:"## Plantilla DoD — Go"`
Ciclo de vida completo (TODO→IN PROGRESS→ON HOLD→DONE): `docs/asana-workflow.md:"## Ciclo de Vida"`
