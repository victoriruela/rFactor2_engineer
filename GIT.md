# Git Workflow

All git operations in this project are governed by automated hooks and conventions documented here. **Agents and developers must read this file before any git operation.**

## Setup

```bash
# From repo root
powershell -ExecutionPolicy Bypass -NoProfile -File scripts/setup-hooks.ps1
```

This sets `core.hooksPath=.githooks` so Git uses the project's hook scripts.

## Hooks

### `pre-commit`

Runs three stages in sequence. The commit is blocked if any stage fails.

| Stage | Command | What it checks |
|-------|---------|----------------|
| **Go vet** | `go vet ./services/backend_go/...` | Go code correctness (shadow vars, printf args, etc.) |
| **Go test** | `go test ./services/backend_go/... -count=1 -short` | Unit tests pass (no Ollama required) |
| **Expo lint** | `cd apps/expo_app && npx tsc --noEmit` | TypeScript type checking |

Integration tests (tagged `integration`) are excluded from the pre-commit hook because they require Ollama and take ~2 minutes. Run them manually before opening a PR.

### `commit-msg`

Validates the commit message against [Conventional Commits](https://www.conventionalcommits.org/) format. Uses a shell script (no Node/commitlint dependency).

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
fix(agents): handle empty telemetry gracefully
docs: update AGENTS.md with Go architecture
test(e2e): add upload flow test
build: add go.mod dependencies
chore: update Expo SDK
release: v1.1.0
```

## Linting

### Go

The project uses `go vet` for correctness and `staticcheck` (optional) for deeper analysis.

```bash
# From services/backend_go/
go vet ./...
```

### TypeScript (Expo)

```bash
# From apps/expo_app/
npx tsc --noEmit
npx eslint .
```

## Branching & Semantic Release

| Branch | Tag on merge | Example |
|--------|-------------|---------|
| `develop` | Release Candidate `vX.Y.Z-rc.N` | `v1.1.0-rc.1` |
| `main` | Full version `vX.Y.Z` | `v1.1.0` |

See `AGENTS.md` → "Development Methodology" → "Semantic Release" for SemVer rules.

### Branching Workflow — MANDATORY

1. **`main`** is the production branch. Never commit directly to main.
2. **`develop`** is the integration branch. Must be synced to main before starting new work.
3. **Feature branches**: branch from `develop` as `feature/<name>`, develop, then merge back to `develop`.
4. **Testing**: after merging to `develop`, run full test suite + manual validation.
5. **Release**: create `release/vX.Y.Z` from `develop`, merge to `main`, tag, and deploy.
6. **Post-release**: merge `main` back to `develop`, then start next feature.

```
main ←── release/vX.Y.Z ←── develop ←── feature/<name>
```

Agents must follow this workflow. Direct commits to `main` or `develop` are only allowed for documentation-only changes.

## Bypassing Hooks

Hooks should **never** be bypassed during normal development. If a hook fails:

1. Fix the issue (lint error, failing test, bad commit message)
2. Stage fixes and retry the commit

For exceptional cases (e.g., emergency hotfix with known failing unrelated test), the supervisor agent must document the justification in the commit message body.
