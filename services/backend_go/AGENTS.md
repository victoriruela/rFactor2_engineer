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

## AI Agent Pipeline

Pipeline en `internal/agents/pipeline.go` — seis agentes en secuencia:

### 1. Translation Agent (una vez, cacheado)
Prompt: `TRANSLATOR_PROMPT` en `internal/agents/prompts.go`.
Traduce nombres de sección/parámetro nuevos al español. Resultados guardados en `data/param_mapping.json`.

### 2. Driving Analysis Agent
Prompt: `DRIVING_PROMPT`.
Input: resumen de telemetría enriquecido (con análisis por zonas) + stats de sesión.
Output: 5 puntos de mejora de conducción con valores numéricos reales, organizados por **curvas numeradas** ("Curva 1", "Curva 2"…) con tipo de curva (horquilla, chicane, ese rápida…). Compara la misma curva entre vueltas. Prohibido sugerir cambios de setup.

### 3. Telemetry Domain Specialists (goroutines concurrentes) — NUEVO
Dos agentes expertos por dominio de telemetría, ejecutados en paralelo:

**Braking Expert** (`BRAKING_EXPERT_PROMPT`):
- Analiza zonas de frenada: eficiencia, distribución de temp de frenos, trail braking, consistencia entre vueltas.
- Output JSON: `{"findings":[{"finding","recommendation","affected_sections"}], "summary"}`.

**Cornering/Balance Expert** (`CORNERING_EXPERT_PROMPT`):
- Analiza equilibrio en curvas: subviraje/sobreviraje, grip por rueda, ride heights, roll, tyre temps, tracción en salida.
- Output JSON: `{"findings":[{"finding","recommendation","affected_sections"}], "summary"}`.

Los hallazgos de estos expertos se inyectan como contexto adicional en los prompts de los especialistas de setup y del ingeniero jefe.

### 4. Section Specialist Agents (goroutines concurrentes)
Prompt: `SECTION_AGENT_PROMPT` (enriquecido con `{telemetry_insights}`).
Un agente por sección via `sync.WaitGroup`. Secciones procesadas: `GENERAL, FRONTWING, REARWING, BODYAERO, SUSPENSION, CONTROLS, ENGINE, DRIVELINE, FRONTLEFT, FRONTRIGHT, REARLEFT, REARRIGHT`.
Secciones omitidas: `BASIC, LEFTFENDER, RIGHTFENDER`. Parámetros `Gear*Setting` también omitidos.
Input: telemetría completa + **hallazgos de expertos de telemetría** + parámetros actuales de la sección + lista de params fijos.
Output JSON: `{"items":[{"parameter","new_value","reason"}], "summary"}`.

### 5. Chief Engineer Agent
Prompt: `CHIEF_ENGINEER_PROMPT` (enriquecido con `{telemetry_insights}`).
Consolida todos los informes de especialistas junto con los hallazgos de los expertos de telemetría. Reglas clave:
- Revisa TODAS las propuestas vs. telemetría completa y hallazgos de expertos
- Aprueba cambios con mérito técnico; rechaza redundantes o contradictorios
- **Ownership de reason**: acepta sin cambios → copia reason del especialista; modifica → escribe su propio reason referenciando datos de telemetría
- Impone simetría de ejes (FL≈FR, RL≈RR) salvo que telemetría justifique asimetría
- `chief_reasoning` es **obligatorio siempre**, debe incluir referencias a hallazgos de telemetría
Output JSON: `{"full_setup":{"sections":[…]}, "chief_reasoning":"…"}`.

### Response Formatting
Combina recomendaciones del chief con setup original, calcula porcentajes de cambio. Secciones sin cambios propuestos se **excluyen** del output. El campo `telemetry_analysis` contiene el texto formateado de los expertos de telemetría para mostrar en el frontend.

### Zone Segmentation (zones.go) — NUEVO
`BuildEnhancedTelemetrySummary()` genera un resumen de telemetría enriquecido que incluye:
1. **Resumen general**: canales disponibles, stats de sesión, min/max/avg por canal.
2. **Comparación por vueltas**: tabla con tiempo, velocidad media/max, acelerador/freno.
3. **Análisis por zonas de la mejor vuelta**: cada frenada, curva, tracción y recta con datos detallados (velocidad, freno, G-forces, temps de freno, ride heights, tyre temps, grip por rueda, indicadores de sub/sobreviraje).
4. **Consistencia entre vueltas**: número de frenadas y curvas por vuelta.

## Data Flow

1. Archivos subidos → guardados en `data/{session_id}/`
2. Telemetría parseada → mapa de canales `map[string][]float64`
3. GPS extraído para circuit map (por defecto una vuelta y submuestreado a 2000 puntos máx.)
4. Stats por vuelta calculados (velocidad, acelerador, freno, RPM, combustible, desgaste, temps)
5. Telemetría submuestreada (~50 puntos/vuelta, top 100 columnas) → CSV string para IA
5b. `telemetry_series` para frontend se limita por backend a 12000 muestras máximas para evitar payloads gigantes en `/api/session_telemetry`.
6. Resumen enriquecido construido: overview + comparación por vueltas + análisis por zonas + consistencia
7. Resumen + mapa de setup → `pipeline.Analyze()`
8. Pipeline multi-agente (driving → telemetry specialists [goroutines] → setup specialists [goroutines] → chief)
9. Resultados formateados con nombres amigables + porcentajes de cambio + análisis de telemetría → respuesta JSON

Constantes de submuestreo: `PARSING_CONSTANTS.md:"## AI Subsampling"`

## File Parsing

### `.mat` (parser Go puro)
MoTeC i2 MATLAB Level 5. Parseo binario directo sin CGo. Extrae canales de struct fields. Alinea todos los canales a la longitud de `Session_Elapsed_Time`. Aplica GPS smoothing y filtrado de vueltas incompletas.

### `.csv`
MoTeC CSV export. 14 líneas de metadata, línea 15 headers, línea 16 unidades, datos desde línea 17. Columnas → float64. GPS smoothing aplicado.
Offsets exactos: `PARSING_CONSTANTS.md:"## CSV Format"`

### `.svm`
rFactor 2 setup. Formato INI-like con `[Section]` y `key=value`. Prueba UTF-16 primero (común en rF2), fallback a UTF-8. Valores con `//` comentarios: `223//N/mm` → `cleanValue()` devuelve `N/mm`.

## Test Infrastructure

### Mocking strategy

| Capa | Approach | Motivo |
|------|----------|--------|
| `.mat` parsing binario | Fixture files reales | Parser Go puro, se prueba con inputs binarios conocidos |
| Llamadas HTTP a Ollama | `httptest.NewServer` mock | No determinista, lento, requiere Ollama; cubierto por integration tests |
| Parsers CSV/SVM en handler tests | **Archivos reales** — no mockeados | Mockear oculta la lógica del parser |
| Pipeline de agentes en handler tests | Mockeado | Solo el boundary LLM; todo el data pipeline corre real |

### Test layout

```
internal/parsers/       *_test.go       # mat, csv, svm, gps, laps
internal/agents/        *_test.go       # pipeline (Ollama mockeado), specialist, chief
internal/handlers/      *_test.go       # upload, session, analysis (agentes mockeados)
internal/ollama/        client_test.go
e2e/                                    # Tests E2E contra servidor real (Ollama requerido)
```

Integration tests (requieren `llama3.2:latest` corriendo): `go test ./... -tags=integration`
