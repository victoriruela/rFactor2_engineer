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

Task status transitions use `update_tasks` with `add_projects` containing the target section GID, or a dedicated move-to-section call.

### MCP tool failure protocol — MANDATORY

The `mcp_asana-mcp_*` tools authenticate via a token stored in the JetBrains IDE config file. That token **expires every hour**. The IDE **caches it at startup** and does not reload it mid-session.

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
       config, but JetBrains has cached the old token. Please restart
       the IDE (File → Invalidate Caches / Restart, or close and reopen
       the project), then ask me to continue."
    ► Wait for the user to confirm restart before doing anything else.

NEVER create a workaround Python script that calls the Asana API or MCP
endpoint directly. NEVER silently bypass the MCP tools.
```

### Creating the board sections (one-time setup)

If `get_project(project_id, include_sections=True)` returns fewer than four sections, create the missing ones using `create_project` with the `sections` array, or via the Asana web UI. The four required section names are exactly: `To Do`, `In Progress`, `In Review`, `Done`.

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

## Development Environment

**Docker is the canonical development environment for this project.** Do NOT use the host Python installation for running tests or lint — the host may have incompatible package versions (e.g. Python 3.13 + pandas).

### Quick start (first time)

```bash
# Build the test image (one-time, or after requirements changes)
docker compose --profile test build test

# Start the full app stack
docker compose up --build

# Pull the LLM model into the Ollama container (one-time)
docker compose exec ollama ollama pull llama3.2:latest
```

### Running tests (always use Docker)

```bash
# Unit tests — fast, no Ollama required (~3s in container)
docker compose --profile test run --rm test

# Unit tests with extra args (e.g. -k filter, -x stop-on-first-fail)
docker compose --profile test run --rm test pytest tests/ --ignore=tests/integration -v -k "my_test"

# Lint
docker compose --profile test run --rm test ruff check app/ frontend/ tests/

# Integration tests — real LLM, requires ollama container running with llama3.2:latest (~3min)
docker compose --profile test run --rm test pytest -m integration -v

# E2E API tests — requires backend container running at :8000
docker compose --profile test run --rm test pytest e2e/api/ -v
```

The `test` service bind-mounts the full source tree at `/app`, so **code changes are reflected immediately without rebuilding** the image. Only rebuild (`docker compose --profile test build test`) when `requirements.txt` or `requirements-dev.txt` change.

### App services

| Service | URL | Start command |
|---------|-----|---------------|
| Backend | http://localhost:8000 | `docker compose up backend` |
| Frontend | http://localhost:8501 | `docker compose up frontend` |
| Ollama | http://localhost:11434 | `docker compose up ollama` |
| All | — | `docker compose up --build` |

## Test Infrastructure

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

Rules and operational playbook for all agentic (multi-subagent) development work on this project.

---

### Phase Specification Format

All work is organized in **phases**. A phase is a coherent unit of work (e.g., "Add .ld file support", "Refactor AI pipeline to streaming") that produces one Release Candidate when merged to `develop`. The supervisor receives a phase spec as input — either from the user or from a higher-level planning step.

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

The supervisor uses this spec to:
- Create Asana tasks with the correct dependency graph
- Determine which tasks can be parallelized (those with no pending upstream dependencies)
- Write subagent prompts scoped to each task
- Resolve merge conflicts in the context of the phase goal

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
  8. Run full test suite on develop (unit + integration + E2E)
  9. If tests fail → fix on develop, commit fix
  10. Tag Release Candidate: vX.Y.Z-rc.N
  11. Update Asana project status: "Phase complete — RC tagged"
```

---

### Asana Task Structure

Tasks are created and managed via the **`mcp_asana-mcp_*` tools only** — never via custom scripts or direct HTTP calls.

#### Pre-flight checklist

Before creating any task:
1. Call `get_project("1213839935179235", include_sections=True)` to retrieve the four section GIDs (`To Do`, `In Progress`, `In Review`, `Done`).
2. If a section is missing, stop and create it (or ask the user to create it in the Asana web UI).
3. Confirm the token is valid (if the previous step failed, follow the **MCP tool failure protocol** above).

#### Creating tasks

Use `create_tasks` with `default_project` as a **top-level tool parameter** (NOT inside the task objects) and `section_id` inside each task pointing to `To Do`:

> ⚠️ **CRITICAL**: `default_project` is a separate top-level argument to the `create_tasks` tool, not a field inside each task object. If placed inside the task, the tool silently ignores it and creates the task with no project.

Call signature:

```
mcp_asana-mcp_create_tasks(
  default_project = "1213839935179235",   ← TOP-LEVEL, not inside tasks[]
  tasks = [
    {
      "name": "[Phase Name] Task: <task name>",
      "notes": "<description>\n\nFiles: <files>\nPhase: <phase>",
      "section_id": "<to_do_section_gid>"   ← inside each task object
    }
  ]
)
```

**Dependency ordering**: Tasks without dependencies are created first. Then tasks with dependencies pass `add_dependencies` referencing the GIDs returned by the first batch.

#### Moving tasks between sections

Use `update_tasks` with `add_projects` to move a task into a new section:

| Transition | Action |
|------------|--------|
| Created → To Do | supply `section_id` in `create_tasks` |
| → In Progress | `update_tasks` → `add_projects: [{project_id, section_id: in_progress_gid}]` + `add_comment`: "Assigned to subagent" |
| → In Review | `add_comment`: "Subagent committed. Reviewing and merging." |
| → Done | `update_tasks` → `completed: true` + `add_comment`: "Merged in \<sha\>" |

#### Querying tasks

Use `get_tasks(project="1213839935179235")` to list all tasks. Check `completed` and `memberships[].section.name` to identify the current state and compute the ready frontier.

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
2. Follow TDD: write unit tests FIRST (in tests/), verify they fail,
   then implement. Commit tests before implementation.
3. Write E2E tests at the end if your task adds/changes an endpoint
   or UI behavior. E2E tests must pass before you stop.
4. All commits must use Conventional Commit format (see GIT.md).
   The pre-commit hook will enforce lint + build + test.
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
(Be aware of potential overlap with sibling tasks — the supervisor
will handle merge conflicts, but minimize unnecessary changes to
shared files.)
```

---

### Merge Protocol (Supervisor)

#### Simple merge (no conflicts)

```bash
cd /path/to/repo                          # main working directory
git checkout develop
git merge .worktrees/<task-slug>          # fast-forward or clean merge
git worktree remove .worktrees/<task-slug>
```

#### Conflict merge

When two parallel subagents touched the same files:

1. **Attempt merge**: `git merge <branch>` — git marks conflict markers
2. **Read the phase spec** to understand the intended behavior of both tasks
3. **Read both diffs**: `git diff develop...<branch-A>` and `git diff develop...<branch-B>`
4. **Reconcile**: produce a version that includes both implementations:
   - If both modified the same function differently → combine both behaviors
   - If both added code to the same location → include both additions in logical order
   - If one renamed/moved code the other modified → apply the modification to the new location
   - **Never discard one side** — both tasks were approved in the phase spec
5. **Test**: run `python -m pytest tests/ --ignore=tests/integration -q` on the reconciled code
6. **Commit** the merge resolution with message: `chore: merge <task-A> and <task-B> (conflict reconciled)`

#### Post-merge validation

After every merge into develop:
- Run `python -m ruff check app/ frontend/ tests/ e2e/` (lint)
- Run `python -m pytest tests/ --ignore=tests/integration -q` (unit tests)
- If either fails, fix immediately on develop before proceeding to the next task

---

### Semantic Release

- **`develop`**: every completed phase creates a Release Candidate tag (`vX.Y.Z-rc.N`)
- **`main`**: every merge from develop creates a full version tag (`vX.Y.Z`) following [SemVer](https://semver.org/):
  - **Patch** (`Z`): bug fixes, no API changes
  - **Minor** (`Y`): new features, backward-compatible
  - **Major** (`X`): breaking changes
- Tags are created with `git tag` and the corresponding GitHub Release via `gh release create`
- The version bump type is specified in the phase spec

---

### Test-Driven Development (TDD)

- Subagents must write unit tests for every function/behavior they implement **before** writing the implementation
- Tests live in `tests/` mirroring the `app/` structure (e.g., `tests/core/test_ai_agents.py`)
- Implementation is written only after tests are in place and confirmed to fail (red → green)
- Subagent commits should be ordered: test commit first, then implementation commit
- The pre-commit hook enforces that all unit tests pass before any commit is accepted

### End-to-End Testing

- E2E tests are written at the **end** of the same task that delivers the feature — not deferred to a separate task
- Subagents **cannot signal task completion** if any E2E test fails; the worktree must not be handed back until the suite is green
- Two E2E topologies are supported for this project:
  - **API**: pytest-based HTTP tests against `localhost:8000` (using `httpx` or `requests`); files in `e2e/api/`
  - **Web**: [Maestro](https://maestro.mobile.dev/) flows against the Streamlit frontend at `localhost:8501`; files in `e2e/web/`

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
[ ] Post-merge lint + tests pass
[ ] Asana status updated: Done
[ ] All tasks complete → full test suite green
[ ] RC tagged on develop
[ ] Asana project status updated
```
