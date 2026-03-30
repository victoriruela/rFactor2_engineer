---
name: asana-rest-api
description: >
  Use when the user asks to "create Asana task", "update Asana board",
  "Asana project", "track in Asana", "add to Asana", "list Asana tasks",
  "move task to done", "Asana sprint", "create tasks with dependencies",
  "set up Asana", "check Asana status", "Asana board", "Asana section",
  "batch create tasks", or any Asana project management operation.
  Direct REST API integration using PAT from project .env file.
version: 1.0.0
---

# Asana REST API Skill

Direct Asana REST API integration using a Personal Access Token (PAT) stored in the project's `.env` file. Replaces the broken MCP connector.

## Setup

One-time per project:

```bash
python3 .claude/skills/asana-rest-api/scripts/asana.py init --pat "0/your_token_here" --project "PROJECT_GID"
```

This validates the PAT and writes `ASANA_PAT` and `ASANA_PROJECT_GID` to `.env`. The `.env` file is already in `.gitignore`.

To get a PAT: https://app.asana.com/0/developer-console → Create new token.

## CLI Reference

All commands output JSON to stdout. Errors go to stderr with exit code 1.

```bash
SCRIPT=".claude/skills/asana-rest-api/scripts/asana.py"
```

### Auth & Config

| Command | Description |
|---------|-------------|
| `python3 $SCRIPT init --pat "0/..." [--project GID]` | Store PAT in .env, validate |
| `python3 $SCRIPT status` | Show user, workspace, default project |

### Read Operations

| Command | Description |
|---------|-------------|
| `python3 $SCRIPT list-projects` | List workspace projects |
| `python3 $SCRIPT get-sections --project GID` | List sections in a project |
| `python3 $SCRIPT list-tasks --project GID [--section GID] [--completed true/false]` | List tasks |
| `python3 $SCRIPT get-task --task GID` | Full task details + subtasks |
| `python3 $SCRIPT search --text "query" [--project GID]` | Search tasks (max 100 results) |

### Write Operations

| Command | Description |
|---------|-------------|
| `python3 $SCRIPT create-task --name "..." [--project GID] [--section GID] [--description "..."] [--due YYYY-MM-DD] [--start YYYY-MM-DD] [--assignee me]` | Create one task |
| `python3 $SCRIPT create-tasks --json '{...}'` | Batch create with dependency resolution |
| `python3 $SCRIPT update-task --task GID [--name "..."] [--completed true] [--due YYYY-MM-DD]` | Update task fields |
| `python3 $SCRIPT move-task --task GID --section GID` | Move task to section |
| `python3 $SCRIPT add-dependency --task GID --depends-on GID1,GID2` | Set task dependencies |
| `python3 $SCRIPT create-section --project GID --name "..."` | Create a new section |
| `python3 $SCRIPT add-comment --task GID --text "..."` | Comment on a task |
| `python3 $SCRIPT delete-task --task GID` | Delete a task |

All `--project` flags fall back to `ASANA_PROJECT_GID` from `.env` if omitted.

## Workflow: Create Sprint Board with Dependencies

```bash
# 1. Get section GIDs
python3 $SCRIPT get-sections --project 1213839378254274

# 2. Batch create tasks with $N dependency references
python3 $SCRIPT create-tasks --json '{
  "project": "1213839378254274",
  "section": "TODO_SECTION_GID",
  "tasks": [
    {"name": "1.1 — Data layer", "description": "...", "due": "2026-04-01"},
    {"name": "1.2 — Parser", "depends_on": ["$0"], "due": "2026-04-02"},
    {"name": "2.1 — Rendering", "section": "OTHER_SECTION_GID", "depends_on": ["$0", "$1"], "due": "2026-04-03"}
  ]
}'
```

In the `depends_on` array, `$0` refers to the first task created in this batch, `$1` to the second, etc. Regular GIDs can also be mixed in. Dependencies are set after all tasks are created.

Per-task `section` overrides the top-level default.

## Workflow: Move Tasks Through Board

```bash
# Move task to "In Progress"
python3 $SCRIPT move-task --task TASK_GID --section IN_PROGRESS_GID

# Mark complete and move to "Done"
python3 $SCRIPT update-task --task TASK_GID --completed true
python3 $SCRIPT move-task --task TASK_GID --section DONE_GID
```

## Error Handling

| Error | Meaning | Fix |
|-------|---------|-----|
| `no_pat` | No ASANA_PAT in .env or environment | Run `init --pat "0/..."` or add to .env |
| `unauthorized` (401) | PAT is invalid or revoked | Create a new PAT at developer console |
| `HTTP 429` | Rate limited (150 req/min) | Script auto-retries with Retry-After (up to 3x) |
| `no_project` | No project GID provided or configured | Use `--project GID` or set ASANA_PROJECT_GID in .env |
| `connection_failed` | Network error | Check internet / Asana status |

## Environment Variables

Stored in project `.env` (already in `.gitignore`):

```env
ASANA_PAT=0/your_personal_access_token
ASANA_PROJECT_GID=1213839378254274
```

These can also be set as actual environment variables, which take precedence over `.env`.
