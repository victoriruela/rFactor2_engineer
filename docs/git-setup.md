# Git Setup — rFactor2 Engineer

Referencia de hooks y configuración de Git. Consultada bajo demanda.

---

## Comandos de Setup

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup-hooks.ps1
```

En shell (alternativo):

```bash
git config core.hooksPath .githooks
```

---

## Hooks Git (Enforcement)

El monorepo usa `core.hooksPath=.githooks` con tres hooks:

### `pre-commit`

Ejecuta quality gates rápidos por dominio antes de cada commit:

- Go: `go vet ./services/backend_go/...` + `go test ./services/backend_go/...`
- Expo: `cd apps/expo_app && npx expo lint` (si hay cambios en apps/)

### `commit-msg`

Enforce de Conventional Commits. Formato obligatorio:

```
feat(scope): descripcion
fix(scope): descripcion
chore(scope): descripcion
test(scope): descripcion
refactor(scope): descripcion
```

### `pre-push`

- Valida la política de ramas destino (ver tabla abajo).
- Ejecuta E2E cuando el push afecta `develop` o `main`.

---

## Política de Ramas (Enforcement por Hook)

| Rama origen | Puede ir a | Bloqueado hacia |
|-------------|------------|-----------------|
| `feature/*` | `develop` | `main` (bloqueado) |
| `fix/*` | `develop` | `main` (bloqueado) |
| `hotfix/*` | `main`, `develop` | — |
| `develop` | `main` | — (solo Supervisor) |
