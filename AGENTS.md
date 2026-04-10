# AGENTS.md — rFactor2 Engineer

Read this file first. Mandatory entry point for all agents.

> **ASANA MANDATE — MANDATORY, ALWAYS**
>
> Every non-trivial development task **must** be tracked in Asana before work begins.
>
> 1. Create (or find) the task in project GID `1213839935179235` **before writing any code**.
> 2. Move to **In Progress** when work begins and to **Done** only after validation is complete.
> 3. Multi-step work: break into sub-tasks with dependencies. See `SUPERVISOR.md:"## Loop de Despacho"`.
>
> Project GIDs and section IDs: `ASANA_CONSTANTS.md` | Plugin docs and token refresh: `ASANA.md`

> **WORKFLOW GUARDRAIL — MANDATORY, ALWAYS**
>
> Before any non-trivial implementation, the agent must execute this checklist in order:
>
> 1. **Task first**: create or locate the Asana task and move it to **In Progress** before substantial work starts.
> 2. **Column discipline**: keep the task aligned with the real board state at all times. In this project the working sections are `Pending`, `In Progress`, `On Hold`, and `Done`. Do not invent intermediate states that do not exist on the board.
> 3. **Parallelization decision**: explicitly check whether exploration, code search, file reading, or independent sub-problems can run in parallel.
> 4. **Use subagents when decomposition helps**: if there are independent discovery tracks or a task can be split into read-only investigation plus implementation, use subagents or parallel read-only tool calls instead of serial manual exploration.
> 5. **Comment and transition on blockers**: if blocked, create the corresponding fix or follow-up task when needed, move the current task to `On Hold`, and leave a comment describing the blocker.
> 6. **Close cleanly**: after validation, move the task to `Done`, mark it completed, and leave a comment with the validation summary and commit SHA when applicable.
>
> If any step above has not been performed yet, do it immediately before continuing.

> **DOCUMENTATION MAINTENANCE MANDATE — MANDATORY**
>
> Any modification to implementation or infrastructure **must** update this file in the same commit:
> - `File Map` — add/rename/remove entries when files change
> - API changes → also update `docs/openapi.yaml`
> - Deployment changes → also update `docs/deployment.md`
> - Architecture/Data Flow changes → update the diagram below

---

## Project Summary

rFactor2 Engineer analyzes sim-racing telemetry (MoTeC `.mat`/`.csv`) and vehicle setup files (`.svm`) using a multi-agent LLM pipeline (4 agents) to produce driving feedback and setup recommendations. All user-facing output is in **Spanish (Castellano)**.

**Stack**: Go 1.22+ (Gin) + Expo web (React Native Web), deployed as a single Linux amd64 binary via `go:embed`.

## Architecture

```
Browser  ├── GET /          → Expo web (embedded from apps/expo_app/dist/ via go:embed)
         └── /api/*         → Gin handlers
                                ├── Parsers       (.mat / .csv / .svm)
                                ├── AI Pipeline   (Translation → Driving → Telemetry Specialists → Setup Specialists → Chief)
                                └── Ollama client (HTTP, :11434)
```

Entry point: `services/backend_go/cmd/server/main.go`
Full topology & ports: `NETWORK_CONSTANTS.md`
AI pipeline detail: `services/backend_go/AGENTS.md:"## AI Agent Pipeline"`

## File Map

```
services/backend_go/
  cmd/server/main.go              # Entry: Gin, routes, go:embed, graceful shutdown
  internal/handlers/              # upload.go  session.go  analysis.go  setup_handler.go  models.go  tracks.go
  internal/parsers/               # mat.go  csv.go  svm.go  gps.go  laps.go
  internal/agents/                # pipeline.go  prompts.go  zones.go  pipeline_reasoning_test.go
  internal/ollama/client.go       # Direct Ollama HTTP client
  internal/domain/                # telemetry.go  setup.go  analysis.go
  internal/config/config.go       # Env var bindings (RF2_PORT, OLLAMA_*, etc.)
  internal/middleware/            # session.go  cors.go
  data/param_mapping.json         # Internal → Spanish friendly name map (auto-extended by Translation Agent)
  data/fixed_params.json          # Locked params list (AI agents must not change these)

apps/expo_app/
  app/(tabs)/                     # index.tsx  upload.tsx (Datos)  analysis.tsx  tracks.tsx  telemetry.tsx
  src/api/                        # client.ts  index.ts  (axios, all /api/* calls)
  src/components/                 # CircuitMap.tsx  SetupTable.tsx
  src/store/useAppStore.ts        # Zustand global state
  src/utils/                      # setupValueParser.ts  labelTranslator.ts

docs/
  openapi.yaml                    # Full API spec (all endpoints + request/response schemas)
  deployment.md                   # GCP host, Nginx, TLS, release procedure
  release_checklist.md            # QA steps before cutting a release

Root reference files:
  CONSTANTS.md          # Index of all constant files
  NETWORK_CONSTANTS.md  # Ports, hosts, URLs
  LLM_CONSTANTS.md      # Model, temperature, providers (Ollama, Jimmy)
  PARSING_CONSTANTS.md  # CSV offsets, GPS smoothing, lap filtering
  SETUP_CONSTANTS.md    # Sections, parameter types, fixed params
  ASANA_CONSTANTS.md    # Asana GIDs
  GIT.md                # Commit conventions, hooks, branching rules
  SUPERVISOR.md         # Supervisor loop, merge protocol, worktree commands
  SUBAGENT.md           # Subagent protocol, quality gates
  ASANA.md              # Asana MCP plugin docs and token refresh procedure
```

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_MODEL` | `llama3.2:latest` | Model tag for all LLM calls |
| `OLLAMA_API_KEY` | *(unset)* | Bearer token for remote/cloud Ollama |
| `RF2_PORT` | `8080` | Gin server listen port |
| `RF2_DATA_DIR` | `./data` | Session uploads directory |
| `RF2_LOG_LEVEL` | `info` | zerolog level (debug/info/warn/error) |

Extended provider config and numeric defaults: `LLM_CONSTANTS.md`

## Key Implementation Patterns

**Value cleaning**: `cleanValue("223//N/mm")` → splits on `//`, uses right part (unit annotation stripped).
**Numeric extraction**: `extractNumeric("223 N/mm")` → `223.0` (used for change-% computation).
**LLM JSON extraction**: `extractJSON()` — brace-depth counter + trailing-comma cleanup on messy LLM output.
**Section name resolution**: LLM may return Spanish friendly names; reverse-map resolves back to internal.
**Ollama auto-start**: `ensureOllamaRunning()` → health GET → starts `ollama serve` if absent, waits 15 s. Skipped when custom `OLLAMA_BASE_URL` is set.
**Ollama cloud auth**: `Authorization: Bearer <OLLAMA_API_KEY>` injected per-request when key is set.
**Specialist normalization**: `normalizeSpecialistReport()` maps Jimmy alternate keys (`recomendaciones`, `parametro`, `nuevo_valor`, `motivo`) → canonical `items[{parameter, new_value, reason}]`.
**Chief-item normalization**: same pattern; also accepts `newValue`, `nuevoValor`, `parametro`, `motivo`.
**Reason sanitization**: strips prompt-template artifacts; fallback chain: chief reason → specialist reason → generic Spanish string.
**Merge strategy**: build from specialist proposals first; chief overrides only for params it explicitly returns.
**Change-% normalization**: `computeChangePct()` returns `0.0%` when `new_value` is empty or semantically unchanged vs `old_value`.
**Setup value units policy**: setup specialists and chief receive/display physical values from `CleanValue()` (never click indices); post-processing normalizes `new_value` to unit-bearing strings and defaults to `deg` when units are missing.
**Driving analysis scope**: driving agent analyzes all laps jointly to detect repeatable driving patterns; recommendations can be global or curve-specific, always grounded in telemetry numbers.
**Circuit map rendering**: telemetría prioriza la vuelta seleccionada para el mapa; backend extrae una sola vuelta por defecto para `circuit_data` y frontend corta solo discontinuidades abruptas (paridad con Python `lap_xy`) para evitar saltos entre vueltas.
**Telemetry payload cap**: `telemetry_series` is evenly downsampled server-side to at most 12000 samples to keep `/api/session_telemetry` web responses within practical size.
**Axle symmetry**: post-processing pass enforces FL≈FR and RL≈RR unless telemetry data justifies asymmetry.
**Reason-value coherence**: final post-processing rebuilds each setup reason from the applied old→new values (after guardrails/symmetry) and regenerates chief reasoning from the final change list to prevent contradictory narratives.
**Reason text hygiene**: reason post-processing strips duplicated trace prefixes (`de <old> a <new>`) and normalizes common mojibake accent artifacts before presenting final Spanish output.
**File-based session save/load (frontend)**: Sessions and locked parameters are saved/loaded as JSON files on the user's local system via the "Datos" tab. No server-side persistence of session state or locked params. Session files use format `{version:1, session_id, saved_at, analysis_result, full_setup, locked_parameters}`. Locked params files use format `{version:1, saved_at, locked_parameters}`.
**Locked params exclusion**: parámetros fijados se excluyen del `setup` antes de enviar contexto a especialistas y jefe; además se filtra cualquier propuesta residual sobre esos parámetros como defensa extra.
**Session scope**: all `/api/` routes scoped to `X-Client-Session-Id` header / `rf2_session_id` cookie.
**Datos tab layout**: Upload section + session management (save/load JSON) + locked params management (save/load JSON) + session info display + two-column layout: setup completo (left) + parámetros fijados (right).

## Language

All user-facing output (driving analysis, setup recommendations, parameter names) is in **Spanish (Castellano)**. Prompts explicitly instruct the LLM to respond in Spanish. The Translation Agent produces Spanish-friendly parameter names.

## Quick Dev Start

```bash
# Backend
cd services/backend_go && go run ./cmd/server    # :8080
# Frontend
cd apps/expo_app && npx expo start --web          # :8081
```

Full test commands: `SUBAGENT.md:"## Quality Gates"` | Build artifact: `README.md:"## Building"`

## Asana MCP Failure Protocol — MANDATORY

When any `mcp_asana-mcp-api_*` call fails with `invalid_token`:

```
1. python "$env:USERPROFILE\.claude\asana-mcp\scripts\asana_mcp.py" auth
   python "$env:USERPROFILE\.claude\asana-mcp\scripts\asana_mcp.py" update-mcp
2. Retry the MCP tool immediately.
3. If it still fails: STOP. Tell the user the IDE must be restarted.
```

**NEVER** bypass MCP tools or call the Asana API directly. Full plugin docs: `ASANA.md`

## Execution Guardrail

For every non-trivial task, follow this operating sequence:

1. **Asana preflight**: create or find the task, retrieve the relevant section GIDs if needed, and move the task to `In Progress` before editing code.
2. **Parallel discovery**: inspect whether the task benefits from parallel read-only work. If yes, use subagents and/or parallel tool calls for search and context gathering.
3. **Focused implementation**: only after the task is tracked and the discovery strategy is decided, edit the minimum required files.
4. **Validation**: run the appropriate compile, test, or export steps.
5. **Asana closure**: update the task with the outcome, move it to `Done`, and only then finish the turn.

This sequence is mandatory even when the fix itself is small; the only exception is a truly trivial request that does not change code, files, configuration, or workflow state.

## Reference Index

Load only when your task requires it — use the grep-syntax references to jump directly to the relevant section.

| Topic | Reference |
|-------|-----------|
| API endpoints — full spec | `docs/openapi.yaml:"paths:"` |
| GCP host, Nginx, TLS, deploy steps | `docs/deployment.md:"## Runtime Topology"` |
| Ports, hosts, base URLs | `NETWORK_CONSTANTS.md` |
| LLM model, temperature, providers | `LLM_CONSTANTS.md` |
| CSV header offsets, GPS smoothing, lap filtering | `PARSING_CONSTANTS.md:"## CSV Format"` |
| Setup sections, parameter types, fixed params | `SETUP_CONSTANTS.md:"## Setup Sections"` |
| Asana project GID, section GIDs | `ASANA_CONSTANTS.md` |
| Git commit format, hooks, branching | `GIT.md:"## Commit Message Format"` |
| Supervisor loop, merge protocol, worktrees | `SUPERVISOR.md:"## Loop de Despacho"` |
| Subagent protocol, quality gates | `SUBAGENT.md:"## Loop de Trabajo"` |
| AI pipeline (4 agents, prompts, data flow) | `services/backend_go/AGENTS.md:"## AI Agent Pipeline"` |
| Go test layout, mocking strategy | `services/backend_go/AGENTS.md:"## Test Infrastructure"` |
| Frontend components, screens, state | `apps/expo_app/AGENTS.md` |
| All constants index | `CONSTANTS.md` |

