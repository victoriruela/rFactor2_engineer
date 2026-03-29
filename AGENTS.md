# AGENTS.md - rFactor2 Engineer

Complete context for any AI agent working on this project. Read this file first before making changes.

## Project Summary

rFactor2 Engineer analyzes sim-racing telemetry (MoTeC `.mat`/`.csv`) and vehicle setup files (`.svm`) using a multi-agent LLM pipeline to produce driving technique feedback and setup change recommendations. All output is in Spanish (Castellano).

## Architecture

```
User (Browser)
    |
Streamlit Frontend (:8501)        ← frontend/streamlit_app.py
    |  HTTP calls to localhost:8000
FastAPI Backend (:8000)           ← app/main.py
    |
    ├── Telemetry Parser          ← app/core/telemetry_parser.py
    │     parse_mat_file(), parse_csv_file(), parse_svm_file()
    |
    └── AI Agent Pipeline         ← app/core/ai_agents.py (class AIAngineer)
          |  LangChain → ChatOllama
          Ollama LLM Server (:11434)
```

**Startup sequence**: Backend (`uvicorn app.main:app --reload`) + Frontend (`streamlit run frontend/streamlit_app.py`). Ollama is auto-started by the backend on first analysis if not running.

## File Map

```
rFactor2_engineer/
├── app/
│   ├── main.py                    # FastAPI server, /analyze endpoint, data pipeline
│   └── core/
│       ├── ai_agents.py           # AIAngineer class, prompts, LLM orchestration
│       ├── telemetry_parser.py    # .mat, .csv, .svm parsers
│       ├── param_mapping.json     # Internal→friendly name translation (116 entries)
│       └── fixed_params.json      # Parameters locked from AI modification (28 entries)
├── frontend/
│   └── streamlit_app.py           # Streamlit UI, file upload, results display
├── .streamlit/
│   └── config.toml                # maxUploadSize = 20000
├── tests/                         # Unit + integration test suite (pytest)
│   ├── conftest.py                # Shared fixtures (DataFrames, SVM content, setup dicts)
│   ├── core/
│   │   ├── test_telemetry_parser.py  # 20 tests: CSV, SVM, .mat, _filter_incomplete_laps
│   │   └── test_ai_agents.py         # 29 tests: pure functions + AIAngineer (mocked LLM)
│   ├── integration/
│   │   ├── conftest.py            # Auto-skip guard if Ollama/llama3.2 unavailable
│   │   └── test_ai_pipeline.py    # 3 tests: full AI pipeline with real LLM (opt-in)
│   ├── test_main.py               # 12 tests: all FastAPI endpoints (real parsers, mocked AI)
│   └── fixtures/
│       ├── sample.csv             # 2-lap MoTeC CSV with GPS + telemetry columns
│       └── sample.svm             # Minimal rFactor2 setup file
├── e2e/
│   ├── api/
│   │   ├── conftest.py            # httpx async client, auto-skip if server offline
│   │   └── test_endpoints.py      # 5 tests against live backend (:8000)
│   └── web/
│       ├── upload_telemetry.yaml  # Maestro Web flow: file upload → telemetry tab
│       └── ai_analysis.yaml       # Maestro Web flow: AI analysis → results visible
├── data/                          # Runtime: uploaded session files (uuid dirs)
├── models/                        # Optional: local .gguf model files
├── pytest.ini                     # asyncio_mode=auto, testpaths=tests, markers
├── requirements.txt               # Python runtime dependencies
├── requirements-dev.txt           # Test dependencies (pytest, httpx, pytest-mock, etc.)
├── ASANA.md                       # Asana MCP plugin docs
├── asana-mcp-plugin.zip           # Asana MCP plugin (install to ~/.claude/asana-mcp/)
├── CONSTANTS.md                   # Index of domain constant files
├── SPECIFICATION.md               # Original project spec
├── README.md                      # User-facing docs (Spanish)
├── Dockerfile                     # Multi-stage build (backend + frontend targets)
├── docker-compose.yml             # 3-service orchestration (ollama, backend, frontend)
├── .dockerignore                  # Build context exclusions
├── GIT.md                         # Git workflow, hooks, commit conventions, linting
├── pyproject.toml                 # Ruff linter configuration
├── package.json                   # Node devDeps (husky + commitlint)
├── commitlint.config.js           # Conventional commits rule config
└── .husky/                        # Git hooks (pre-commit, commit-msg)
```

## Dependencies

```
fastapi                    # API server
uvicorn                    # ASGI runner
streamlit                  # Frontend UI
python-multipart           # File upload support for FastAPI
pandas                     # DataFrame operations
numpy                      # Numeric/stats
scipy                      # .mat file parsing (scipy.io.loadmat)
langchain>=1.2.0           # LLM framework
langchain-core>=0.3.0      # PromptTemplate, StrOutputParser
langchain-ollama           # ChatOllama integration
python-dotenv              # .env loading
plotly                     # Interactive circuit map
matplotlib                 # Listed but unused
requests                   # HTTP calls (Ollama API, frontend→backend)
```

**System dependency**: [Ollama](https://ollama.com/) must be installed. The app auto-starts it and auto-detects its binary on Windows (`LOCALAPPDATA/Programs/Ollama/ollama.exe`, `ProgramFiles/Ollama/ollama.exe`) and PATH.

**Python**: 3.9+ (no 3.10+ syntax used).

## Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `OLLAMA_MODEL` | `llama3.2:latest` | Model tag passed to ChatOllama |
| `RF2_API_URL` | `http://localhost:8000` | Backend URL used by Streamlit frontend |

Set in `.env` at project root (loaded by python-dotenv). In Docker, these are set via `docker-compose.yml`.

## API Endpoints

### `POST /analyze`
Main analysis endpoint. Accepts multipart form:
- `telemetry_file`: `.mat` or `.csv` (MoTeC export)
- `svm_file`: `.svm` (rFactor 2 setup)
- `model` (optional): Ollama model tag override
- `fixed_params` (optional): JSON string array of locked parameter names

Returns `AnalysisResponse` with: `circuit_data`, `issues_on_map`, `driving_analysis`, `setup_analysis`, `full_setup`, `session_stats`, `laps_data`, `agent_reports`, `telemetry_summary_sent`, `chief_reasoning`.

### `GET /sessions`
Lists uploaded sessions (directories in `data/` with both `.mat`/`.csv` and `.svm` files).

### `GET /models`
Returns available Ollama models via `GET /api/tags` on Ollama.

### `POST /cleanup`
Deletes all `.mat` and `.svm` files from `data/`, removes empty dirs.

## AI Agent Pipeline

The `AIAngineer.analyze()` method runs this sequence:

### 1. Translation Agent (once, cached)
**Prompt**: `TRANSLATOR_PROMPT`
Translates any new section/parameter names to Spanish-friendly names. Results saved to `param_mapping.json`.

### 2. Driving Analysis Agent
**Prompt**: `DRIVING_PROMPT`
Input: telemetry summary + session stats.
Output: 5 driving improvement points with real numeric values. Strictly forbidden from suggesting setup changes.

### 3. Section Specialist Agents (one per setup section)
**Prompt**: `SECTION_AGENT_PROMPT`
Runs once per section (GENERAL, FRONTWING, REARWING, BODYAERO, SUSPENSION, CONTROLS, ENGINE, DRIVELINE, FRONTLEFT, FRONTRIGHT, REARLEFT, REARRIGHT, etc.). Skips BASIC, LEFTFENDER, RIGHTFENDER. Also skips Gear*Setting parameters.
Input: full telemetry + section's current parameters + fixed params list.
Output: JSON with `items` array (parameter, new_value, reason) and `summary`.

### 4. Chief Engineer Agent
**Prompt**: `CHIEF_ENGINEER_PROMPT`
Consolidates all specialist reports into a coherent setup. Rules:
- Permissive: accept specialist recommendations unless contradictory
- Preserve specialist reasoning verbatim when accepting changes
- Enforce symmetry (FL≈FR, RL≈RR) unless telemetry justifies asymmetry
- Respect fixed params absolutely
Output: JSON with `full_setup.sections[]` and `chief_reasoning`.

### Response formatting
`_format_full_setup()` merges chief's recommendations with the original setup data, computing change percentages for display.

## File Parsing

### `.mat` files (`parse_mat_file`)
MoTeC i2 MATLAB export. Uses `scipy.io.loadmat(struct_as_record=False, squeeze_me=True)`. Extracts channels from struct `.Value` fields. Aligns all channels to the length of `Session_Elapsed_Time`. Applies GPS smoothing and incomplete lap filtering.

### `.csv` files (`parse_csv_file`)
MoTeC CSV export. First 14 lines are metadata, line 15 is headers, line 16 is units, data starts line 17. All columns converted to numeric. GPS smoothing applied.

### `.svm` files (`parse_svm_file`)
rFactor 2 setup. INI-like format with `[Section]` headers and `key=value` pairs. Tries UTF-16 first (common for rF2), falls back to UTF-8. Values often contain `//` comments: `223//N/mm` means value is `N/mm` part (cleaned by `_clean_value`).

## Data Flow Through Analysis

1. Files uploaded → saved to `data/{uuid}/`
2. Telemetry parsed → DataFrame with all channels
3. GPS extracted for circuit map (subsampled to 5000 points max)
4. Per-lap stats computed (speed, throttle, brake, RPM, fuel, wear, temps)
5. Telemetry subsampled (~50 points/lap, top 100 columns) → CSV string for AI
6. Summary built: circuit name + session stats + lap summaries + detailed CSV
7. Summary + setup dict → `AIAngineer.analyze()`
8. Multi-agent pipeline runs (driving → specialists → chief)
9. Results formatted with friendly names + change percentages → JSON response

## Param Mapping System

`app/core/param_mapping.json` maps internal names → Spanish friendly names:
- Sections: `FRONTLEFT` → `"Neumático Delantero Izquierdo"`
- Parameters: `CamberSetting` → `"Caída (Camber)"`

Auto-extended by the Translation Agent when new parameters are encountered. The reverse mapping (friendly → internal) is used to match LLM output back to internal names.

## Fixed Parameters System

`app/core/fixed_params.json` is a JSON array of parameter names that AI agents must not modify. Managed by the Streamlit UI. Passed to every specialist and chief prompt as a constraint. See `CONSTANTS.md` for the current default list.

## Asana MCP Integration

See [`ASANA.md`](ASANA.md) for full details. Plugin zip at `asana-mcp-plugin.zip`. Manages OAuth2 auth and token injection into Claude Desktop, Claude CLI, VS Code Copilot, and JetBrains Copilot configs.

## Constants

All hardcoded values (ports, paths, thresholds, parameter lists, telemetry channels, Asana config) are documented in [`CONSTANTS.md`](CONSTANTS.md). Reference that file when working with specific numeric values or configuration.

## Key Patterns

**Value cleaning**: Setup values like `223//N/mm` → cleaned to `N/mm` via `_clean_value()` which splits on `//` and takes the right side.

**Numeric extraction**: `_extract_numeric("223 N/mm")` → `223.0`. Used for computing change percentages.

**LLM JSON extraction**: `_get_json_from_llm()` parses JSON from potentially messy LLM output using brace-depth counting and trailing-comma cleanup.

**Section name resolution**: LLM may return friendly names instead of internal names. Both `AIAngineer.analyze()` and `_format_full_setup()` use reverse-mapping dicts to handle this.

**Ollama auto-start**: `_ensure_ollama_running()` checks health via `GET /api/tags`, starts `ollama serve` as background process if needed, waits up to 15s.

## Language

All user-facing output (driving analysis, setup recommendations, parameter names) is in **Spanish (Castellano)**. Prompts explicitly instruct the LLM to respond in Spanish. The Translation Agent produces Spanish-friendly parameter names.

## Test Infrastructure

### Running tests

```bash
# Install test dependencies (one-time)
pip install -r requirements-dev.txt

# Unit tests — fast, no Ollama required (~0.5s)
pytest tests/ --ignore=tests/integration -v

# Integration tests — real LLM, requires ollama + llama3.2:latest (~3min)
pytest -m integration -v

# E2E API tests — requires backend running at :8000
pytest e2e/api/ -v

# E2E Web tests — requires backend + Streamlit + Maestro installed
maestro test e2e/web/upload_telemetry.yaml
```

### System requirement

`llama3.2:latest` (= 3b, 2.0 GB) is a **hard project requirement** — the same model the app uses in production. Pull it once:

```bash
ollama pull llama3.2:latest
```

Note: `llama3.2:3b` and `llama3.2:latest` are the same weights (`:latest` is the canonical alias). Always use `:latest` as the tag to avoid 404 errors on machines that only pulled via the default alias.

### Mocking strategy

| Layer | Approach | Reason |
|---|---|---|
| `scipy.io.loadmat` | Mocked in unit tests | Real MoTeC `.mat` binary format cannot be reproduced with `scipy.io.savemat`; mock accurately mirrors `mat_struct.Value` interface |
| `ChatOllama` / LLM | Mocked in unit tests | Non-deterministic, slow, requires Ollama; covered by `tests/integration/` with real model |
| `parse_csv_file` / `parse_svm_file` in endpoint tests | **Real files** — not mocked | Mocking parsers hides ~200 lines of GPS/lap/subsampling logic in `app/main.py` |
| `ai_engineer.analyze` in endpoint tests | Mocked | Only the LLM boundary; all data pipeline before it runs for real |

### Test layout

```
tests/
├── core/test_telemetry_parser.py   # CSV, SVM, .mat parsing; _filter_incomplete_laps
├── core/test_ai_agents.py          # Pure functions + AIAngineer unit tests
├── test_main.py                    # All endpoints (real parsers, mocked AI)
└── integration/test_ai_pipeline.py # Full AI pipeline with real Ollama (opt-in)

e2e/
├── api/test_endpoints.py           # Live backend smoke tests
└── web/*.yaml                      # Maestro Web flows (Streamlit UI)
```

## Docker

### Quick start

```bash
docker compose up --build
```

Services:
- **Frontend**: http://localhost:8501
- **Backend**: http://localhost:8000
- **Ollama**: http://localhost:11434

### First run — pull the model

After the Ollama container is up, pull the required model:

```bash
docker compose exec ollama ollama pull llama3.2:latest
```

### Architecture

```
┌─────────────┐    ┌──────────┐    ┌────────┐
│  Frontend   │───▶│ Backend  │───▶│ Ollama │
│  :8501      │    │  :8000   │    │ :11434 │
└─────────────┘    └──────────┘    └────────┘
  RF2_API_URL       OLLAMA_BASE_URL
```

### Volumes

| Mount | Purpose |
|-------|---------|
| `./data` → `/app/data` | Session uploads (persist across restarts) |
| `./app/core/param_mapping.json` | Translation cache (generated at runtime) |
| `./app/core/fixed_params.json` | User-locked parameters |
| `ollama_data` (named) | Downloaded model weights |

### Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Multi-stage build (targets: `backend`, `frontend`) |
| `docker-compose.yml` | Orchestrates all 3 services |
| `.dockerignore` | Excludes data/, tests/, .git/ from build context |

## Git Workflow

All commit conventions, hooks (husky + commitlint), linting (ruff), and branching rules are documented in [`GIT.md`](GIT.md). **Read that file before any git operation.**

Key points:
- **Pre-commit hook** runs lint → build → unit tests (blocks commit on failure)
- **Commit-msg hook** enforces [Conventional Commits](https://www.conventionalcommits.org/) format
- Hooks must **never** be bypassed (`--no-verify` is forbidden)

## Development Methodology

Rules for all agentic (multi-subagent) development work on this project.

### 1. Task Planning (Asana)

- All project upgrades must be planned as a group of Asana tasks **before any work begins**
- Tasks must have explicit dependency edges so the supervisor can determine which are safe to parallelize
- Only tasks with no unresolved upstream dependencies may be handed to a subagent at a given moment

### 2. Git Isolation (Worktrees)

- Each subagent works in its own isolated git worktree (`git worktree add`)
- Worktrees branch off the current `develop` HEAD at task start
- Subagents must **not** push or merge — they commit only; the supervisor performs all merges
- **Every subagent prompt must explicitly state: "Commit your work and stop. Do not merge or push."**

### 3. Asana Status Lifecycle (Supervisor, Atomic)

The supervisor updates Asana task status at exactly three moments, synchronously:

| Moment | Status transition |
|---|---|
| Before handing task to subagent | → In Progress |
| After subagent delivers its result | → In Review |
| After supervisor finalizes the merge | → Done |

No other agent or process should write task status.

### 4. Merge Protocol (Supervisor)

- Supervisor waits for the subagent's commit before proceeding
- All merges are performed by the supervisor, never by the subagent
- When parallel subagents have touched overlapping files, the supervisor merges both implementations intelligently — preserving all intended behavior from each, consistent with the overall phase specification
- Conflicts are never resolved by discarding one side; both contributions must be reconciled

### 5. Semantic Release

- **`develop`**: every merge creates a Release Candidate tag (`vX.Y.Z-rc.N`)
- **`main`**: every merge creates a full version tag (`vX.Y.Z`) following [SemVer](https://semver.org/):
  - **Patch** (`Z`): bug fixes, no API changes
  - **Minor** (`Y`): new features, backward-compatible
  - **Major** (`X`): breaking changes

### 6. Test-Driven Development (TDD)

- Subagents must write unit tests for every function/behavior they implement **before** writing the implementation
- Tests live in `tests/` mirroring the `app/` structure (e.g., `tests/core/test_ai_agents.py`)
- Implementation is written only after tests are in place and confirmed to fail (red → green)
- Subagent commits should be ordered: test commit first, then implementation commit

### 7. End-to-End Testing

- E2E tests are written at the **end** of the same task that delivers the feature — not deferred to a separate task
- Subagents **cannot signal task completion** if any E2E test fails; the worktree must not be handed back until the suite is green
- Two E2E topologies are supported for this project:
  - **API**: pytest-based HTTP tests against `localhost:8000` (using `httpx` or `requests`); files in `e2e/api/`
  - **Web**: [Maestro](https://maestro.mobile.dev/) flows against the Streamlit frontend at `localhost:8501`; files in `e2e/web/`
