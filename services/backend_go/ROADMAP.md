# ROADMAP - Backend Go

Ver etiquetas de Stage en `AGENTS.md` (raíz).

---

## [STAGE-1-ENV] Fase 1 — Entorno y Bootstrap

### Tarea 1.1 — Bootstrap del servicio Go
**Descripción**: Inicializar el módulo Go (`go mod init`), estructura de paquetes (`cmd/`, `internal/`,
`e2e/`, `config/`, `testdata/`), servidor HTTP con Gin, endpoints `GET /api/health` y `GET /api/readiness`,
configuración por entorno (`.env`/variables de entorno), logging estructurado (`zerolog`).
Configurar `go:embed` para servir la web app Expo en `/`.
**Archivos**: `cmd/server/main.go`, `internal/config/config.go`, `internal/health/handler.go`, `internal/web/embed.go`
**Depende de**: ninguna

---

## [STAGE-2-CORE] Fase 2 — Parsers y API Core

### Tarea 2.1 — Parser de archivos .csv (MoTeC)
**Descripción**: Migrar la lógica de `parse_csv_file` de Python a Go. Leer CSV con 14 líneas de metadatos,
headers en línea 15, datos desde línea 17. Suavizado de GPS (outlier threshold 1.5×std, rolling window 11).
Filtrado de vueltas incompletas (excluir lap 0, excluir >110% mediana duración).
**Archivos**: `internal/telemetry/csv_parser.go`, `internal/telemetry/csv_parser_test.go`
**Depende de**: Tarea 1.1

### Tarea 2.2 — Parser de archivos .svm (rFactor2 setup)
**Descripción**: Migrar la lógica de `parse_svm_file`. Formato INI con secciones `[SECTION]` y pares
`key=value`. Soportar encoding UTF-16 y UTF-8 con fallback.
**Archivos**: `internal/telemetry/svm_parser.go`, `internal/telemetry/svm_parser_test.go`
**Depende de**: Tarea 1.1

### Tarea 2.3 — Parser de archivos .mat (MATLAB)
**Descripción**: Migrar la lógica de `parse_mat_file`. Leer archivos MATLAB Level 5 binarios.
Extraer canales, alinear por longitud, renombrar canales comunes, suavizar GPS, filtrar vueltas.
**Archivos**: `internal/telemetry/mat_parser.go`, `internal/telemetry/mat_parser_test.go`
**Depende de**: Tarea 1.1

### Tarea 2.4 — Upload chunked de archivos
**Descripción**: Migrar endpoints POST `/api/uploads/init`, PUT `/api/uploads/{id}/chunk`,
POST `/api/uploads/{id}/complete`. Streaming a disco sin cargar en RAM.
**Archivos**: `internal/upload/handler.go`, `internal/upload/handler_test.go`
**Depende de**: Tarea 1.1

### Tarea 2.5 — Gestión de sesiones (SQLite)
**Descripción**: CRUD de sesiones con aislamiento por `X-Client-Session-Id` header/cookie.
Endpoints GET `/api/sessions`, GET `/api/sessions/{id}/file/{filename}`, POST `/api/cleanup`.
Persistencia en SQLite.
**Archivos**: `internal/sessions/handler.go`, `internal/sessions/repository.go`, `internal/sessions/handler_test.go`
**Depende de**: Tarea 1.1

### Tarea 2.6 — Track storage (SHA256 dedup)
**Descripción**: Migrar track upload/list/retrieve. Almacenamiento JSON con deduplicación SHA256.
**Archivos**: `internal/tracks/storage.go`, `internal/tracks/handler.go`, `internal/tracks/storage_test.go`
**Depende de**: Tarea 1.1

---

## [STAGE-3-LLM] Fase 3 — Pipeline LLM en Go

### Tarea 3.1 — Cliente HTTP Ollama
**Descripción**: Implementar cliente Go para Ollama REST API (`POST /api/chat`).
Soporte para streaming y non-streaming. Timeout, reintentos, JSON parsing con cleanup
de trailing commas.
**Archivos**: `internal/llm/client.go`, `internal/llm/types.go`, `internal/llm/client_test.go`
**Depende de**: Tarea 1.1

### Tarea 3.2 — Cliente HTTP Jimmy (chatjimmy.ai)
**Descripción**: Implementar cliente Go para chatjimmy.ai REST API. Headers Referer/Origin
obligatorios. Parsing de respuesta plain text con sanitizado de `<|stats|>` tags.
Runtime config desde `jimmy_runtime_config.v1.json`.
**Archivos**: `internal/llm/jimmy_client.go`, `internal/llm/jimmy_client_test.go`
**Depende de**: Tarea 3.1

### Tarea 3.3 — Translation Agent
**Descripción**: Agente que mapea nombres de parámetros internos → español usando LLM.
Carga y actualiza `param_mapping.json`. Solo se invoca cuando hay parámetros nuevos.
**Archivos**: `internal/analysis/translation_agent.go`, `internal/analysis/translation_agent_test.go`
**Depende de**: Tarea 3.1

### Tarea 3.4 — Driving Analysis Agent
**Descripción**: Agente que genera 5 puntos de mejora de pilotaje curva a curva, citando
valores numéricos reales de telemetría. Sin propuestas de setup.
**Archivos**: `internal/analysis/driving_agent.go`, `internal/analysis/driving_agent_test.go`
**Depende de**: Tarea 3.1

### Tarea 3.5 — Section Specialist Agents (concurrentes)
**Descripción**: ~14 agentes (uno por sección de setup: GENERAL, FRONTWING, REARWING, SUSPENSION, etc.).
Se ejecutan en paralelo con `sync.WaitGroup` + goroutines. Cada uno propone `{parameter, new_value, reason}`.
Normalización de variantes de esquema JSON (keys en español/inglés).
**Archivos**: `internal/analysis/specialist_agents.go`, `internal/analysis/specialist_agents_test.go`
**Depende de**: Tarea 3.1

### Tarea 3.6 — Chief Engineer Agent
**Descripción**: Consolida reportes de especialistas. Enforce de simetría axial (FRONTLEFT↔FRONTRIGHT,
REARLEFT↔REARRIGHT). Descarta textos internos no válidos. Produce `full_setup` + `chief_reasoning`.
**Archivos**: `internal/analysis/chief_agent.go`, `internal/analysis/chief_agent_test.go`
**Depende de**: Tarea 3.5

### Tarea 3.7 — Pipeline Orchestrator
**Descripción**: Orquesta la secuencia completa: init LLM → update mappings → driving analysis →
specialists (parallel) → chief engineer → format full setup → response.
Endpoint POST `/api/analyze` y POST `/api/analyze_session`.
**Archivos**: `internal/analysis/pipeline.go`, `internal/analysis/pipeline_test.go`
**Depende de**: Tarea 3.3, Tarea 3.4, Tarea 3.6

---

## [STAGE-4-WEB] Fase 4 — Embed Expo Web

### Tarea 4.1 — Integrar build Expo en Go binary
**Descripción**: Configurar `go:embed` para incluir la build de Expo (`apps/expo_app/dist/`)
en el binario Go. Servir como SPA (fallback a index.html para rutas del cliente).
**Archivos**: `internal/web/embed.go`, `internal/web/embed_test.go`
**Depende de**: Tarea 1.1

---

## [STAGE-5-QA] Fase 5 — Tests y Hardening

### Tarea 5.1 — Integration tests del pipeline
**Descripción**: Tests que recorran el pipeline completo con fixtures de test (sample.csv + sample.svm).
Verificar que el response contenga driving_analysis, setup sections, chief_reasoning.
**Archivos**: `e2e/pipeline_test.go`
**Depende de**: Tarea 3.7

### Tarea 5.2 — E2E: Upload → Analyze → Verify
**Descripción**: Test E2E que suba archivos via chunked upload, lance análisis, y verifique
la respuesta completa incluyendo circuit map data.
**Archivos**: `e2e/full_flow_test.go`
**Depende de**: Tarea 5.1

---

## [STAGE-6-RELEASE] Fase 6 — Release

### Tarea 6.1 — Build Linux y scripts de deploy
**Descripción**: Script para `GOOS=linux GOARCH=amd64 go build -ldflags "-s -w"`.
Actualizar `scripts/deploy_gcp.ps1` para copiar binario en vez de docker-compose.
Actualizar nginx conf para proxy a `:8080`.
**Archivos**: `scripts/build-linux.ps1`, `scripts/deploy_gcp.ps1`, `deploy/nginx-rfactor2_engineer.conf`
**Depende de**: Tarea 5.2
