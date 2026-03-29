# Git Workflow

All git operations in this project are governed by automated hooks and conventions documented here. **Agents and developers must read this file before any git operation.**

## Setup

```bash
# Install Node dependencies (husky + commitlint)
npm install

# Install Python dev dependencies (ruff + pytest)
pip install -r requirements-dev.txt
```

`npm install` triggers `husky` via the `prepare` script, which installs the git hooks automatically.

## Hooks

### `pre-commit`

Runs three stages in sequence. The commit is blocked if any stage fails.

| Stage | Command | What it checks |
|-------|---------|----------------|
| **Lint** | `python -m ruff check app/ frontend/ tests/ e2e/` | Python code quality (unused imports, style, errors) |
| **Build** | `python -c "from app.main import app"` | App is importable (no syntax or import errors) |
| **Test** | `python -m pytest tests/ --ignore=tests/integration -q` | Unit tests pass (no Ollama required) |

Integration tests (`tests/integration/`) are excluded from the pre-commit hook because they require Ollama and take ~2 minutes. Run them manually before opening a PR.

### `commit-msg`

Validates the commit message against [Conventional Commits](https://www.conventionalcommits.org/) using `commitlint`.

## Commit Message Format

```
type(scope): subject
```

### Allowed types

| Type | When to use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, no code change |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `test` | Adding or updating tests |
| `build` | Build system or external dependencies |
| `ci` | CI/CD configuration |
| `chore` | Maintenance, no production code change |
| `revert` | Revert a previous commit |
| `release` | Version release |

### Rules

- **Header** (full first line) max 100 characters
- **Scope** is optional but encouraged (e.g., `feat(parser): add .ld file support`)

### Examples

```
feat(telemetry): add .ld file parsing support
fix(ai): handle empty telemetry gracefully
docs: update AGENTS.md with docker section
test(e2e): add upload flow maestro test
build: dockerize project with compose
chore: update ruff config
release: v1.1.0
```

## Linting

The project uses [ruff](https://docs.astral.sh/ruff/) for Python linting. Configuration is in `pyproject.toml`.

```bash
# Check for issues
ruff check app/ frontend/ tests/ e2e/

# Auto-fix safe issues
ruff check app/ frontend/ tests/ e2e/ --fix
```

### Configured rules

- **Selected**: `E` (pycodestyle errors), `F` (pyflakes), `W` (pycodestyle warnings)
- **Ignored globally**: `E501` (line too long), `E741` (ambiguous variable name)
- **Per-file ignores**: `E402` for `frontend/streamlit_app.py`, `app/main.py`, `tests/test_main.py`

## Branching & Semantic Release

| Branch | Tag on merge | Example |
|--------|-------------|---------|
| `develop` | Release Candidate `vX.Y.Z-rc.N` | `v1.1.0-rc.1` |
| `main` | Full version `vX.Y.Z` | `v1.1.0` |

See `AGENTS.md` → "Development Methodology" → "Semantic Release" for SemVer rules.

## Bypassing Hooks

Hooks should **never** be bypassed during normal development. If a hook fails:

1. Fix the issue (lint error, failing test, bad commit message)
2. Stage fixes and retry the commit

For exceptional cases (e.g., emergency hotfix with known failing unrelated test), the supervisor agent must document the justification in the commit message body.
