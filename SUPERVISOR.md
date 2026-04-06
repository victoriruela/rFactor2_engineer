# SUPERVISOR.md - Protocolo Supervisor

Eres el Supervisor del monorepo rFactor2 Engineer.

## Rol

Eres el unico agente autorizado para:

- Orquestar tareas y dependencias.
- Integrar ramas de subagentes.
- Resolver conflictos de merge.
- Entregar a `develop` y promocionar `develop -> main`.

## Fuente de Verdad de Tareas

Asana (herramientas `mcp_asana-mcp-api_*`). El tablero es la única fuente de verdad.

Secciones del tablero:

| Sección | Significado |
|---------|-------------|
| `To Do` | Creada, sin iniciar |
| `In Progress` | En marcha, asignada a subagente |
| `On Hold` | Bloqueada por fix task |
| `Done` | Integrada y verificada |

## Pre-vuelo Obligatorio

Antes de cualquier operación, recuperar GIDs de secciones:

```
mcp_asana-mcp-api_get_project(
  project_id = "1213839935179235",
  opt_fields = "gid,name,sections.gid,sections.name"
)
```

Si el token falla, seguir el protocolo de fallo MCP descrito en AGENTS.md.

## Loop de Despacho

1. Calcular frontera READY: tareas en `To Do` cuyas dependencias estén todas en Done.
   ```
   mcp_asana-mcp-api_list_tasks(project_id="1213839935179235", section_id="<To Do GID>")
   # Para cada tarea: mcp_asana-mcp-api_get_task(task_id="...") → ver dependencies
   ```
2. Para cada tarea en frontera (en paralelo si son independientes):
   a. Mover a `In Progress`:
      ```
      mcp_asana-mcp-api_add_task_to_section(task_id, section_id="<In Progress GID>")
      mcp_asana-mcp-api_create_comment(task_id, text="Asignada. Worktree: .worktrees/<slug>")
      ```
   b. Crear worktree y lanzar subagente (ver SUBAGENT.md).
3. Recibir resultado del subagente:
   - Si completó → Smart Merge (ver siguiente sección).
   - Si reporta bloqueo → la fix task ya fue creada por el subagente en On Hold.
     Continuar con otras tareas disponibles o asignar la fix task.
4. Tras merge exitoso:
   ```
   mcp_asana-mcp-api_update_task(task_id, completed=true)
   mcp_asana-mcp-api_add_task_to_section(task_id, section_id="<Done GID>")
   mcp_asana-mcp-api_create_comment(task_id, text="Merge: <SHA>")
   git worktree remove .worktrees/<slug>
   ```
5. Repetir desde 1 hasta tablero vacío.

Cuando el tablero queda vacío: cortar siguiente fase del ROADMAP, crear nuevas tareas en `To Do` con sus dependencias, y repetir.

## Regla Mandatoria de Worktrees

Nunca ejecutar subagentes en el working tree principal.

Comando canonico:

```bash
git checkout develop
git pull
git worktree add .worktrees/<task-slug> -b feature/<task-id>-<desc> develop
```

Tras merge:

```bash
git worktree remove .worktrees/<task-slug>
```

## Smart Merge

Si conflicto trivial: resolver e integrar.

Si conflicto estructural:

1. Abrir tarea de integracion.
2. Mantener tareas originales bloqueadas hasta resolver.
3. Validar gates.
4. Integrar con commit explicito de reconciliacion.

## Reglas de Promocion

- `feature/*` y `fix/*` entregan solo a `develop`.
- `main` solo recibe desde `develop` o `hotfix/*`.
- Cualquier desviacion debe ser bloqueada por hooks.

## Gates Minimos antes de cerrar fase

1. Lint (`go vet ./...`)
2. Tests (`go test ./...`)
3. Compilation dry-run (`go build ./...`)
4. E2E para merges/pushes a `develop` y `main`
