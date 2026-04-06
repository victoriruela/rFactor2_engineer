# AGENTS.md - rFactor2 Engineer

Complete context for any AI agent working on this project. Read this file first before making changes.

> **ASANA MANDATE — MANDATORY FOR ALL AGENTS, ALWAYS**
>
> Every non-trivial development task **must** be tracked in Asana before work begins.
> This applies regardless of whether the user explicitly mentions Asana.
>
> **Required workflow for any task involving code changes:**
> 1. Before writing a single line, create (or find) the corresponding Asana task in the
>    **"rFactor2 Engineer"** project (GID `1213839935179235`).
> 2. Move the task to **In Progress** when work begins.
> 3. Move to **In Review** after committing; move to **Done** after the user validates.
> 4. For multi-step work, break it down into sub-tasks and respect the dependency graph
>    to maximize parallelism (see "Development Methodology" → "Supervisor Algorithm").
>
> **No exceptions.** Using Asana is how this project tracks progress, enables parallelism,
> and avoids duplicate or conflicting work. Skipping it is treated as a process violation.
> See the full MCP integration details in the "Asana MCP Integration" section below.

> **DOCUMENTATION MAINTENANCE MANDATE — MANDATORY FOR ALL AGENTS**
>
> Any agent that modifies **implementation** (API endpoints, data pipeline, AI agents, parsers, tests)
> or **infrastructure / deployment** (Nginx, GCP scripts, release flow, environment variables)
> **must** update this file in the same commit that introduces the change. Sections to keep current:
> - `File Map` — add / rename / remove entries when files change
> - `API Endpoints` — reflect any new, changed, or removed route
> - `GCP Deployment` — reflect any change to topology, scripts, credentials, or release procedure
> - `Development Environment` — reflect changes to test commands or build steps
> - `Architecture` / `Data Flow` — reflect structural changes to the pipeline
>
> Stale documentation is treated as a bug.

## Project Summary

rFactor2 Engineer analyzes sim-racing telemetry (MoTeC `.mat`/`.csv`) and vehicle setup files (`.svm`) using a multi-agent LLM pipeline to produce driving technique feedback and setup change recommendations. All output is in Spanish (Castellano).

**Technology stack**: Go backend (Gin) + Expo web frontend (React Native Web) embedded via `go:embed`. Deployed as a single Linux amd64 binary.

## Architecture

```
User (Browser)
    |
Expo Web Frontend (embedded)       ← apps/expo_app/ (served via go:embed at /)
    |  HTTP calls to /api/*
Go API Layer (Gin, :8080)          ← services/backend_go/
    |
  ├── Handlers                   ← services/backend_go/internal/handlers/
  │     upload.go, session.go, analysis.go, models.go, tracks.go
    |
  ├── Parsers                    ← services/backend_go/internal/parsers/
  │     mat.go, csv.go, svm.go
  |
  ├── AI Agent Pipeline          ← services/backend_go/internal/agents/
  │     pipeline.go, translator.go, driving.go, specialist.go, chief.go
  |
  └── Ollama HTTP Client         ← services/backend_go/internal/ollama/
          client.go (direct HTTP, no LangChain)
          |
          Ollama LLM Server (:11434)
```

**Startup**: `go run ./services/backend_go/cmd/server` starts the Gin server on `:8080`, serves the embedded Expo web build at `/` and the API at `/api/*`. Ollama is auto-started on first analysis if not running.

**Build**: `go build -o rfactor2-engineer ./services/backend_go/cmd/server` produces a single Linux binary. The Expo web build is embedded via `go:embed` directive pointing to `apps/expo_app/dist/`.

## File Map

```
rFactor2_engineer/
├── services/backend_go/
│   ├── cmd/
│   │   └── server/
│   │       └── main.go              # Entry point: Gin setup, routes, go:embed, graceful shutdown
│   ├── internal/
│   │   ├── handlers/
│   │   │   ├── upload.go            # Chunked upload: init, chunk, complete
│   │   │   ├── session.go           # Session listing, file download, cleanup
│   │   │   ├── analysis.go          # /api/analyze, /api/analyze_session
│   │   │   ├── models.go            # /api/models (proxy to Ollama /api/tags)
│   │   │   └── tracks.go            # /api/tracks (known circuit metadata)
│   │   ├── parsers/
│   │   │   ├── mat.go               # MATLAB Level 5 .mat parser (pure Go, no CGo)
│   │   │   ├── csv.go               # MoTeC CSV parser (14-line header skip, data from line 17)
│   │   │   ├── svm.go               # rFactor2 .svm INI-like parser (UTF-16/UTF-8 fallback)
│   │   │   ├── gps.go               # GPS smoothing (1.5×std outlier, 11-sample rolling window)
│   │   │   └── laps.go              # Lap filtering (exclude lap 0, exclude >110% median)
│   │   ├── agents/
│   │   │   ├── pipeline.go          # Orchestrates the 4-agent analysis pipeline
│   │   │   ├── translator.go        # Translation Agent: new param names → Spanish
│   │   │   ├── driving.go           # Driving Analysis Agent
│   │   │   ├── specialist.go        # Section Specialist Agents (concurrent goroutines)
│   │   │   ├── chief.go             # Chief Engineer Agent: consolidation + axle symmetry
│   │   │   └── prompts.go           # All LLM prompt templates
│   │   ├── ollama/
│   │   │   └── client.go            # HTTP client for Ollama API (generate, tags, health)
│   │   ├── domain/
│   │   │   ├── telemetry.go         # Telemetry data structures
│   │   │   ├── setup.go             # Setup data structures (sections, params, fixed params)
│   │   │   └── analysis.go          # Analysis request/response types
│   │   ├── config/
│   │   │   └── config.go            # Runtime settings from env vars
│   │   └── middleware/
│   │       ├── session.go           # X-Client-Session-Id header/cookie resolution
│   │       └── cors.go              # CORS configuration
│   ├── data/
│   │   └── param_mapping.json       # Internal→friendly name translation (116 entries)
│   │   └── fixed_params.json        # Parameters locked from AI modification (28 entries)
│   ├── go.mod
│   ├── go.sum
│   ├── AGENTS.md                    # Backend-specific agent guidance
│   ├── SUBAGENT.md
│   ├── SUPERVISOR.md
│   ├── ROADMAP.md
│   └── README.md
├── apps/expo_app/
│   ├── app/
│   │   ├── _layout.tsx              # Root layout (React Navigation)
│   │   ├── index.tsx                # Home / session list screen
│   │   ├── upload.tsx               # File upload screen (chunked)
│   │   ├── analysis.tsx             # Analysis results screen
│   │   └── tracks.tsx               # Track gallery screen
│   ├── components/
│   │   ├── CircuitMap.tsx           # SVG circuit map with issue markers
│   │   ├── SetupTable.tsx           # Setup recommendations table with change %
│   │   ├── DrivingAnalysis.tsx      # Driving feedback card
│   │   ├── FileUploader.tsx         # Chunked upload component
│   │   └── ModelSelector.tsx        # Ollama model dropdown
│   ├── services/
│   │   └── api.ts                   # Axios HTTP client for /api/* endpoints
│   ├── store/
│   │   └── analysisStore.ts         # Zustand state management
│   ├── app.json                     # Expo config
│   ├── package.json
│   ├── tsconfig.json
│   ├── AGENTS.md                    # Frontend-specific agent guidance
│   ├── SUBAGENT.md
│   ├── SUPERVISOR.md
│   ├── ROADMAP.md
│   └── README.md
├── docs/
│   ├── asana-workflow.md            # Full Asana workflow with DoD templates
│   ├── git-setup.md                 # Git hooks for Go/Expo
│   ├── product-spec.md             # Complete product specification
│   ├── openapi.yaml                 # OpenAPI 3.0 spec for all endpoints
│   └── release_checklist.md         # QA checklist for Go binary + Expo web release
├── scripts/
│   ├── run-local-tests.ps1          # Runs go test + jest
│   ├── setup-hooks.ps1              # Sets core.hooksPath=.githooks
│   └── stop-local-tests.ps1         # Kills processes on ports 8080/8081
├── deploy/
│   ├── nginx-rfactor2_engineer.conf # Nginx reverse-proxy config (TLS, Basic Auth, proxy)
│   └── .htpasswd                    # Basic Auth credentials (hashed) for host Nginx
├── data/                            # Runtime: per-client session uploads (not in git)
├── AGENTS.md                        # THIS FILE — complete context for AI agents (keep current)
├── ASANA.md                         # Asana MCP plugin docs
├── ASANA_CONSTANTS.md               # Asana GIDs and constants
├── CONSTANTS.md                     # Index of domain constant files
├── GIT.md                           # Git workflow, hooks, commit conventions
├── SUPERVISOR.md                    # Root supervisor protocol
├── SUBAGENT.md                      # Root subagent protocol
└── README.md                        # User-facing docs (Spanish)
```

## Dependencies

### Go Backend

```
github.com/gin-gonic/gin          # HTTP router + middleware
github.com/rs/zerolog              # Structured JSON logging
modernc.org/sqlite                 # Pure-Go SQLite (session/metadata storage, optional)
golang.org/x/text/encoding/unicode # UTF-16 decoding for .svm files
```

**System dependency**: [Ollama](https://ollama.com/) must be installed. The backend auto-starts it and auto-detects the binary on the current OS PATH.

**Go version**: 1.22+

### Expo Frontend

```
expo ~52                           # Expo SDK
react-native-web                   # Web rendering
@react-navigation/native           # Navigation
axios                              # HTTP client
zustand                            # State management
react-native-svg                   # Circuit map SVG rendering
```

**Node version**: 20+

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2:latest` | Model tag for LLM calls |
| `OLLAMA_API_KEY` | *(unset)* | Bearer token for remote/cloud Ollama |
| `RF2_PORT` | `8080` | Gin server listen port |
| `RF2_DATA_DIR` | `./data` | Session uploads directory |
| `RF2_LOG_LEVEL` | `info` | zerolog level (debug, info, warn, error) |

## API Endpoints

All endpoints under `/api/` that touch the `data/` directory are **session-scoped**: the caller's identity is resolved from the `X-Client-Session-Id` request header or the `rf2_session_id` cookie. Each client sees only its own uploads and sessions.

### Chunked file upload flow

#### `POST /api/uploads/init`
Initiates a resumable file upload. Body: `{"filename": "<name>"}` (JSON).
Returns `{"upload_id", "chunk_size", "filename"}`.

#### `PUT /api/uploads/{upload_id}/chunk?chunk_index=N`
Uploads one raw-body chunk (max `chunk_size` bytes). Must be sent in order (409 if out of sequence).
Default `chunk_size` is **16 MiB**.
Returns `{"upload_id", "chunk_index", "bytes_received"}`.

#### `POST /api/uploads/{upload_id}/complete`
Assembles all chunks into the final file under `data/<client_session_id>/`.
Returns `{"filename", "bytes_received"}`.

### Session management

#### `GET /api/sessions`
Lists complete sessions (directories in `data/<client_session_id>/` with both a telemetry file and a `.svm` file). Returns `{"sessions": [{"id", "telemetry", "svm"}]}`.

#### `GET /api/sessions/{session_id}/file/{filename}`
Downloads a stored session file. Only the telemetry and SVM filenames belonging to that session are accessible (path-traversal guard).

### Analysis

#### `POST /api/analyze`
Direct-upload analysis (no prior chunking required). Accepts multipart form:
- `telemetry_file`: `.mat` or `.csv` (MoTeC export)
- `svm_file`: `.svm` (rFactor 2 setup)
- `model` (optional): Ollama model tag override
- `provider` (optional): LLM provider (default `ollama`)
- `fixed_params` (optional): JSON string array of locked parameter names
- `ollama_base_url` (optional): Override Ollama endpoint
- `ollama_api_key` (optional): Bearer token for remote/cloud Ollama

Returns `AnalysisResponse` with: `circuit_data`, `issues_on_map`, `driving_analysis`, `setup_analysis`, `full_setup`, `session_stats`, `laps_data`, `agent_reports`, `telemetry_summary_sent`, `chief_reasoning`.

#### `POST /api/analyze_session`
Analyzes a previously uploaded stored session (via chunked upload). Form params: `session_id` (required), `model`, `provider`, `fixed_params`, `ollama_base_url` (optional), `ollama_api_key` (optional). Deletes session files after successful analysis. Same `AnalysisResponse` shape.

### Other

#### `GET /api/models`
Returns available Ollama models via `GET /api/tags` on Ollama.
Optional query params: `ollama_base_url`, `ollama_api_key`.

#### `GET /api/tracks`
Returns known circuit metadata (name, country, length, map SVG path).

#### `POST /api/cleanup`
Deletes the current client session's telemetry/setup files and in-progress chunk files.

#### `POST /api/cleanup_all`
Deletes **all** stored artifacts under `data/`. Used by the frontend at startup to guarantee no stale data survives.

## AI Agent Pipeline

The analysis pipeline (`services/backend_go/internal/agents/pipeline.go`) runs this sequence:

### 1. Translation Agent (once, cached)
**Prompt**: `TRANSLATOR_PROMPT`
Translates any new section/parameter names to Spanish-friendly names. Results saved to `param_mapping.json`.

### 2. Driving Analysis Agent
**Prompt**: `DRIVING_PROMPT`
Input: telemetry summary + session stats.
Output: 5 driving improvement points with real numeric values, organized by **numbered curves** ("Curva 1", "Curva 2"...) with curve type description (horquilla, chicane, ese rápida...). Each point compares the same curve across multiple laps, citing real telemetry values. Strictly forbidden from suggesting setup changes.

### 3. Section Specialist Agents (concurrent goroutines)
**Prompt**: `SECTION_AGENT_PROMPT`
Runs once per section (GENERAL, FRONTWING, REARWING, BODYAERO, SUSPENSION, CONTROLS, ENGINE, DRIVELINE, FRONTLEFT, FRONTRIGHT, REARLEFT, REARRIGHT, etc.) via `sync.WaitGroup`. Skips BASIC, LEFTFENDER, RIGHTFENDER. Also skips Gear*Setting parameters.
Input: full telemetry + section's current parameters + fixed params list.
Output: JSON with `items` array (parameter, new_value, reason) and `summary`.
Specialists explicitly acknowledge parameters that are already well-configured.

### 4. Chief Engineer Agent
**Prompt**: `CHIEF_ENGINEER_PROMPT`
Consolidates all specialist reports into a coherent setup via **holistic review**. Rules:
- Reviews ALL specialist proposals against full telemetry + setup context
- Approves changes with technical merit; rejects redundant or contradictory changes
- Detects and corrects physical incoherencies
- **Reason ownership**: if accepting a specialist proposal unchanged → copies specialist reason verbatim; if modifying → writes own detailed reason
- Enforces axle symmetry (FL≈FR, RL≈RR) unless telemetry justifies asymmetry
- Acknowledges parameters that are already correct
- Respects fixed params absolutely
- `chief_reasoning` is **mandatory always**
Output: JSON with `full_setup.sections[]` and `chief_reasoning`.

### Response formatting
Merges chief's recommendations with the original setup data, computing change percentages for display. Sections with zero proposed changes are **excluded** from the output.

## File Parsing

### `.mat` files (pure Go parser)
MoTeC i2 MATLAB Level 5 export. Parses the binary MATLAB format directly without CGo. Extracts channels from struct fields. Aligns all channels to the length of `Session_Elapsed_Time`. Applies GPS smoothing and incomplete lap filtering.

### `.csv` files
MoTeC CSV export. First 14 lines are metadata, line 15 is headers, line 16 is units, data starts line 17. All columns converted to float64. GPS smoothing applied.

### `.svm` files
rFactor 2 setup. INI-like format with `[Section]` headers and `key=value` pairs. Tries UTF-16 first (common for rF2), falls back to UTF-8. Values often contain `//` comments: `223//N/mm` means value is `N/mm` part (cleaned by `cleanValue()`).

## Data Flow Through Analysis

1. Files uploaded → saved to `data/{session_id}/`
2. Telemetry parsed → channel map (`map[string][]float64`)
3. GPS extracted for circuit map (subsampled to 5000 points max)
4. Per-lap stats computed (speed, throttle, brake, RPM, fuel, wear, temps)
5. Telemetry subsampled (~50 points/lap, top 100 columns) → CSV string for AI
6. Summary built: circuit name + session stats + lap summaries + detailed CSV
7. Summary + setup map → `pipeline.Analyze()`
8. Multi-agent pipeline runs (driving → specialists [goroutines] → chief)
9. Results formatted with friendly names + change percentages → JSON response

## Param Mapping System

`services/backend_go/data/param_mapping.json` maps internal names → Spanish friendly names:
- Sections: `FRONTLEFT` → `"Neumático Delantero Izquierdo"`
- Parameters: `CamberSetting` → `"Caída (Camber)"`

Auto-extended by the Translation Agent when new parameters are encountered. The reverse mapping (friendly → internal) is used to match LLM output back to internal names.

## Fixed Parameters System

`services/backend_go/data/fixed_params.json` is a JSON array of parameter names that AI agents must not modify. Managed by the Expo UI. Passed to every specialist and chief prompt as a constraint. See `CONSTANTS.md` for the current default list.

## Asana MCP Integration

See [`ASANA.md`](ASANA.md) for full details.

### Canonical project

The single Asana project for all phases of this repo is **"rFactor2 Engineer"** (GID `1213839935179235`, workspace `1213846793386214`). **Always use this project.** Never create a second project.

### Board layout

The project uses **Board layout** with four fixed sections. These must exist before creating tasks:

| Section | Meaning |
|---------|---------|
| `To Do` | Task created, not yet started |
| `In Progress` | Assigned to a subagent and actively being worked |
| `In Review` | Subagent committed; supervisor is merging |
| `Done` | Merged and verified |

When creating tasks, always supply `section_id` pointing to the `To Do` section GID. Retrieve section GIDs with `get_project(project_id, include_sections=True)`.

### MCP tool failure protocol — MANDATORY

The `mcp_asana-mcp_*` tools authenticate via a token stored in the IDE config file. That token **expires every hour**. The IDE **caches it at startup** and does not reload it mid-session.

When any `mcp_asana-mcp_*` call fails with `invalid_token`:

```
Step 1 — Refresh & re-inject the token (run in terminal):
    python "$env:USERPROFILE\.claude\asana-mcp\scripts\asana_mcp.py" auth
    python "$env:USERPROFILE\.claude\asana-mcp\scripts\asana_mcp.py" update-mcp

Step 2 — Retry the MCP tool immediately (the token in the config file is
    now valid; occasionally the IDE picks it up without a restart).

Step 3 — If the tool still fails:
    ► STOP. Tell the user:
      "The Asana MCP token has been refreshed and written to the IDE
       config, but the IDE has cached the old token. Please restart
       the IDE, then ask me to continue."
    ► Wait for the user to confirm restart before doing anything else.

NEVER create a workaround script that calls the Asana API directly.
NEVER silently bypass the MCP tools.
```

### Creating the board sections (one-time setup)

If `get_project(project_id, include_sections=True)` returns fewer than four sections, create the missing ones. The four required section names are exactly: `To Do`, `In Progress`, `In Review`, `Done`.

## Constants

All hardcoded values (ports, paths, thresholds, parameter lists, telemetry channels, Asana config) are documented in [`CONSTANTS.md`](CONSTANTS.md). Reference that file when working with specific numeric values or configuration.

## Key Patterns

**Value cleaning**: Setup values like `223//N/mm` → cleaned by `cleanValue()` which splits on `//` and takes the right side.

**Numeric extraction**: `extractNumeric("223 N/mm")` → `223.0`. Used for computing change percentages.

**LLM JSON extraction**: `extractJSON()` parses JSON from potentially messy LLM output using brace-depth counting and trailing-comma cleanup.

**Section name resolution**: LLM may return friendly names instead of internal names. Both the pipeline and formatting use reverse-mapping maps to handle this.

**Ollama auto-start**: `ensureOllamaRunning()` checks health via `GET /api/tags`, starts `ollama serve` as background process if needed, waits up to 15s. Skipped when a custom base URL is provided (remote/cloud Ollama).

**Ollama remote/cloud API**: The Ollama client supports targeting a remote server (e.g. Ollama Cloud at `https://ollama.com`). When `apiKey` is provided, `Authorization: Bearer <key>` is injected into requests.

**Jimmy specialist normalization**: `normalizeSpecialistReport()` accepts alternate JSON keys from Jimmy responses (`recomendaciones`, `parametro`, `nuevo_valor`, `motivo`, etc.) and maps them to the canonical `items[{parameter,new_value,reason}]` shape.

**Jimmy chief-item normalization**: Chief engineer section items are normalized through the same canonical shape and accept alternate keys such as `newValue`, `nuevoValor`, `parametro`, and `motivo`.

**Reason sanitization against prompt leakage**: The backend sanitizes `reason` and `chief_reasoning` fields to strip internal/template artifacts. If a chief item reason is invalid, it falls back to the specialist reason; if no specialist reason exists, it uses a safe generic fallback in Spanish.

**Specialist-first consolidation merge**: The final recommendation map is built from specialist proposals first, then chief proposals are applied as overrides for parameters explicitly returned by the chief.

**Deterministic axle symmetry post-processing**: After chief consolidation, the backend enforces symmetry for `FRONTLEFT/FRONTRIGHT` and `REARLEFT/REARRIGHT` when asymmetric values are not explicitly justified by telemetry. Harmonizes to the more conservative value and annotates the reason.

**Frontend ephemeral session policy**: The Expo UI treats uploads as session-local only. No persistent cookie/query-param for client session IDs.

**Frontend page-load cleanup**: At startup, the frontend calls `POST /api/cleanup_all` once to purge stale data.

## Language

All user-facing output (driving analysis, setup recommendations, parameter names) is in **Spanish (Castellano)**. Prompts explicitly instruct the LLM to respond in Spanish. The Translation Agent produces Spanish-friendly parameter names.

## Development Environment

### Quick start

```bash
# Backend (from repo root)
cd services/backend_go
go run ./cmd/server

# Frontend (from repo root, separate terminal)
cd apps/expo_app
npm install
npx expo start --web

# Ensure Ollama has the required model
ollama pull llama3.2:latest
```

### Running tests

```bash
# Go unit tests (from services/backend_go/)
go test ./... -v -count=1

# Go integration tests (requires Ollama running with llama3.2:latest)
go test ./... -v -tags=integration -count=1

# Expo unit tests (from apps/expo_app/)
npm test

# Full suite (from repo root)
powershell -ExecutionPolicy Bypass -NoProfile -File scripts/run-local-tests.ps1
```

### Building the artifact

```bash
# Build Expo web first
cd apps/expo_app
npx expo export --platform web
# Output goes to apps/expo_app/dist/

# Build Go binary with embedded web
cd services/backend_go
GOOS=linux GOARCH=amd64 go build -o ../../rfactor2-engineer ./cmd/server
```

The `cmd/server/main.go` uses `//go:embed ../../apps/expo_app/dist` to embed the entire Expo web build into the binary.

### Services (development)

| Service | URL | Start command |
|---------|-----|---------------|
| Backend (Go) | http://localhost:8080 | `go run ./services/backend_go/cmd/server` |
| Frontend (Expo) | http://localhost:8081 | `cd apps/expo_app && npx expo start --web` |
| Ollama | http://localhost:11434 | `ollama serve` |

## Test Infrastructure

### System requirement

`llama3.2:latest` (3B, ~2.0 GB) is a **hard project requirement** — the same model the app uses in production. Pull it once:

```bash
ollama pull llama3.2:latest
```

### Test layout

```
services/backend_go/
├── internal/parsers/
│   ├── mat_test.go                 # .mat parsing tests
│   ├── csv_test.go                 # CSV parsing tests
│   ├── svm_test.go                 # .svm parsing tests
│   ├── gps_test.go                 # GPS smoothing tests
│   └── laps_test.go                # Lap filtering tests
├── internal/agents/
│   ├── pipeline_test.go            # Full pipeline tests (mocked Ollama)
│   ├── specialist_test.go          # Specialist agent tests
│   └── chief_test.go              # Chief engineer tests
├── internal/handlers/
│   ├── upload_test.go              # Upload endpoint tests
│   ├── session_test.go             # Session endpoint tests
│   └── analysis_test.go            # Analysis endpoint tests (mocked agents)
└── internal/ollama/
    └── client_test.go              # Ollama HTTP client tests

apps/expo_app/
├── __tests__/
│   ├── CircuitMap.test.tsx         # Circuit map component tests
│   ├── SetupTable.test.tsx         # Setup table component tests
│   ├── api.test.ts                 # API client tests (mocked)
│   └── analysisStore.test.ts       # Zustand store tests
```

### Mocking strategy

| Layer | Approach | Reason |
|---|---|---|
| `.mat` binary parsing | Test with fixture files | Pure Go parser tested with known binary inputs |
| Ollama HTTP calls | `httptest.NewServer` mock | Non-deterministic, slow, requires Ollama; covered by integration tests |
| CSV/SVM parsers in handler tests | **Real files** — not mocked | Mocking hides parser logic |
| Agent pipeline in handler tests | Mocked | Only the LLM boundary; all data pipeline runs for real |
| Expo API client | `jest.mock('axios')` | Isolates UI tests from backend |

## GCP Deployment

### Canonical host

- SSH target: `bitor@34.175.126.128`
- Auth: default SSH keypair already configured for current user.
- Nginx binary path: `/usr/sbin/nginx`

### Runtime topology

- Single Go binary running on host, listening on `127.0.0.1:8080`
- Public domains: `telemetria.bot.nu`, `car-setup.com`
- Nginx listens on `:80` and `:443`
- HTTP redirects to HTTPS for both domains
- HTTPS proxy routes:
  - `/` → `http://127.0.0.1:8080` (serves embedded Expo web + API)
  - `/api/*` → `http://127.0.0.1:8080/api/*`
- Nginx enforces HTTP Basic Auth on **all routes**.
- Nginx upload limit: `client_max_body_size 20000M`.
- TLS terminated at host Nginx using Let's Encrypt certs.

### HTTP Basic Auth (current)

- User: `racef1`
- Password: `100fuchupabien`
- Credential file deployed to host: `/etc/nginx/.htpasswd_rfactor2_engineer`
- Source file in repo: `deploy/.htpasswd` (hashed value)

### TLS / Certbot

- Active certificate names: `telemetria.bot.nu`, `car-setup.com`
- Automatic renewal handled by `certbot.timer`.

### Release and deploy procedure

The single binary simplifies deployment:

1. Build the Expo web bundle: `npx expo export --platform web`
2. Build the Go binary: `GOOS=linux GOARCH=amd64 go build -o rfactor2-engineer ./services/backend_go/cmd/server`
3. Tag release: `git tag vX.Y.Z && git push --tags`
4. Upload binary to GCP host via `scp`
5. On host: stop old process, replace binary, start new process
6. Verify health: `curl -u racef1:100fuchupabien https://car-setup.com/api/models`

### Operational notes

- Do not expose the Go binary directly to public interfaces; keep loopback binding and route through Nginx.
- Host memory safeguard: configure persistent swap on the GCP host (`/swapfile`, 2 GiB, `vm.swappiness=10`).
- The `data/` directory on the remote host persists across deploys.

## Git Workflow

All commit conventions, hooks, and branching rules are documented in [`GIT.md`](GIT.md). **Read that file before any git operation.**

Key points:
- **Pre-commit hook** runs lint → build → unit tests (blocks commit on failure)
- **Commit-msg hook** enforces [Conventional Commits](https://www.conventionalcommits.org/) format
- Hooks must **never** be bypassed (`--no-verify` is forbidden)

## Development Methodology

Rules and operational playbook for all agentic (multi-subagent) development work on this project.

---

### Phase Specification Format

All work is organized in **phases**. A phase is a coherent unit of work that produces one Release Candidate when merged to `develop`.

A phase spec must contain:

```
Phase: <short name>
Goal: <what this phase delivers, in 1-2 sentences>
Scope: <which areas of the codebase are affected>
Version bump: patch | minor | major

Tasks:
  1. <task name>
     Description: <what the subagent must implement>
     Files: <expected files to create/modify>
     Depends on: none | <task numbers>

  2. <task name>
     Description: ...
     Files: ...
     Depends on: 1

  3. <task name>
     Description: ...
     Files: ...
     Depends on: none

  (tasks 2 and 3 can run in parallel; task 1 must finish first)
```

---

### Supervisor Algorithm

The supervisor follows this exact loop when executing a phase:

```
PHASE_START:
  1. Parse the phase spec
  2. Create Asana tasks (see "Asana Task Structure" below)
     - One task per spec item, in the correct project
     - Set `add_dependencies` for each task based on "Depends on"
     - All tasks start as incomplete (not started)

EXECUTION_LOOP:
  3. Query Asana for incomplete tasks in this phase's project/section
  4. Identify the READY FRONTIER: tasks whose dependencies are ALL marked Done
  5. If frontier is empty and tasks remain → error (circular dependency or stuck task)
  6. If no tasks remain → go to PHASE_COMPLETE

  For each task in the ready frontier (launch in parallel where possible):
    a. Update Asana task → In Progress (add comment: "Assigned to subagent")
    b. Create a git worktree:
         git worktree add .worktrees/<task-slug> develop
    c. Spawn subagent with the SUBAGENT PROMPT TEMPLATE (see below)
    d. Wait for subagent to complete (it will commit and stop)

  For each completed subagent (process as they finish):
    e. Update Asana task → In Review
    f. Merge the worktree branch into develop (see "Merge Protocol")
    g. If merge succeeds:
         - Update Asana task → Done (add comment with merge commit SHA)
         - Clean up worktree: git worktree remove .worktrees/<task-slug>
    h. If merge has conflicts:
         - Read both diffs + phase spec
         - Produce reconciled version preserving both implementations
         - Commit the reconciliation
         - Update Asana task → Done
         - Clean up worktree

  7. Go to EXECUTION_LOOP (new tasks may now be unblocked)

PHASE_COMPLETE:
  8. Run full test suite on develop (go test + npm test)
  9. If tests fail → fix on develop, commit fix
  10. Tag Release Candidate: vX.Y.Z-rc.N
  11. Ask user to validate RC locally and WAIT for explicit approval
  12. After approval: merge develop → main, create release tag, deploy binary
  13. Update Asana project status: "Phase complete — RC validated and released"
```

---

### Asana Task Structure

Tasks are created and managed via the **`mcp_asana-mcp_*` tools only** — never via custom scripts or direct HTTP calls.

#### Pre-flight checklist

Before creating any task:
1. Call `get_project("1213839935179235", include_sections=True)` to retrieve the four section GIDs.
2. If a section is missing, stop and create it.
3. Confirm the token is valid (if the previous step failed, follow the **MCP tool failure protocol** above).

#### Creating tasks

Use `create_tasks` with `default_project` as a **top-level tool parameter** (NOT inside the task objects) and `section_id` inside each task pointing to `To Do`:

> ⚠️ **CRITICAL**: `default_project` is a separate top-level argument to the `create_tasks` tool, not a field inside each task object. If placed inside the task, the tool silently ignores it.

#### Moving tasks between sections

| Transition | Action |
|------------|--------|
| Created → To Do | supply `section_id` in `create_tasks` |
| → In Progress | `update_tasks` → `add_projects: [{project_id, section_id: in_progress_gid}]` + comment |
| → In Review | comment: "Subagent committed. Reviewing and merging." |
| → Done | `update_tasks` → `completed: true` + comment with merge SHA |

#### Querying tasks

Use `get_tasks(project="1213839935179235")` to list all tasks. Check `completed` and `memberships[].section.name` to identify current state and compute the ready frontier.

---

### Subagent Prompt Template

Every subagent receives this prompt. The supervisor fills in the `{{placeholders}}`.

```
## Task
{{task_description}}

## Files
You are expected to create or modify: {{file_list}}

## Worktree
You are working in: {{worktree_path}}
Your branch: {{branch_name}}

## Rules (mandatory)
1. READ `AGENTS.md` and `GIT.md` before starting.
2. Follow TDD: write unit tests FIRST, verify they fail,
   then implement. Commit tests before implementation.
3. Write E2E tests at the end if your task adds/changes an endpoint
   or UI behavior.
4. All commits must use Conventional Commit format (see GIT.md).
5. Do NOT merge, push, or modify any branch other than your own.
6. When done, commit all work and stop. Report back with:
   - List of commits (SHAs + messages)
   - Summary of what was implemented
   - Any concerns or known limitations

## Context
Phase: {{phase_name}}
Phase goal: {{phase_goal}}
Your task depends on: {{dependency_descriptions_or_none}}
Other parallel tasks in this phase: {{sibling_task_names}}
```

---

### Merge Protocol (Supervisor)

#### Simple merge (no conflicts)

```bash
git checkout develop
git merge .worktrees/<task-slug>
git worktree remove .worktrees/<task-slug>
```

#### Conflict merge

1. **Attempt merge**: `git merge <branch>` — git marks conflict markers
2. **Read the phase spec** to understand the intended behavior of both tasks
3. **Read both diffs**
4. **Reconcile**: produce a version that includes both implementations — **never discard one side**
5. **Test**: run `go test ./services/backend_go/...` and `cd apps/expo_app && npm test`
6. **Commit** the merge resolution

#### Post-merge validation

After every merge into develop:
- Run `go vet ./services/backend_go/...` (lint)
- Run `go test ./services/backend_go/... -count=1` (unit tests)
- Run `cd apps/expo_app && npm test` (frontend tests)
- If any fail, fix immediately on develop before proceeding

---

### Test-Driven Development (TDD)

- Subagents must write unit tests for every function/behavior they implement **before** writing the implementation
- Go tests live alongside source files (`*_test.go`)
- Expo tests live in `__tests__/` directories
- Implementation is written only after tests are confirmed to fail (red → green)
- Subagent commits should be ordered: test commit first, then implementation commit

### End-to-End Testing

- E2E tests are written at the **end** of the same task that delivers the feature
- Subagents **cannot signal task completion** if any E2E test fails
- Two E2E topologies:
  - **API**: Go `httptest` or external HTTP tests against the Gin server
  - **Web**: Playwright or Detox tests against the Expo web app

---

### Quick Reference: Supervisor Checklist

```
[ ] Phase spec received and understood
[ ] Asana tasks created with correct dependencies
[ ] Ready frontier identified
[ ] Subagents spawned with full prompt template
[ ] Asana status updated: In Progress
[ ] Subagent commits received
[ ] Asana status updated: In Review
[ ] Worktree merged into develop (conflicts reconciled if needed)
[ ] Post-merge go test + npm test pass
[ ] Asana status updated: Done
[ ] All tasks complete → full test suite green
[ ] RC tagged on develop
[ ] User asked to validate RC locally
[ ] Binary built and started locally for RC validation
[ ] Explicit user approval received
[ ] Asana project status updated
```
