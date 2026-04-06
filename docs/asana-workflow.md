# Asana Workflow — rFactor2 Engineer

Referencia completa de gestión de tareas. Consultada bajo demanda.
GIDs y protocolo de fallo del token están en el root `AGENTS.md`.

---

## Configuración Inicial del Proyecto

Obtener GIDs de secciones del tablero:

```
mcp_asana-mcp-api_get_project(
  project_id = "1213839935179235",
  opt_fields  = "gid,name,sections.gid,sections.name"
)
```

Si falta alguna sección:

```
mcp_asana-mcp-api_create_section(
  project_id = "1213839935179235",
  name       = "<sección>"
)
```

---

## Estructura de una Tarea

Campos obligatorios al llamar `mcp_asana-mcp-api_create_task`:

- **name**: `[Fase N] Dominio: Nombre descriptivo`
- **projects**: `["1213839935179235"]`
- **notes**: bloque estructurado:

```
## Descripción
<qué implementa el subagente>

## Archivos esperados
<lista de ficheros a crear o modificar>

## Definition of Done
- [ ] Lint/typecheck pasa
- [ ] Tests unitarios pasan
- [ ] Compilation dry-run pasa
- [ ] E2E pasa (si entrega afecta develop o main)
- [ ] Código revisado e integrado en develop por el Supervisor
- [ ] Tarea en sección Done

## Fase
<nombre de la fase>

## Depende de
<GIDs bloqueantes o "ninguna">
```

---

## Creación de Tareas por Fases — Flujo Supervisor

1. Listar tareas sin dependencia (frontera inicial).
2. Crear primero las tareas sin dependencias → obtener sus GIDs.
3. Crear las tareas dependientes apuntando a los GIDs anteriores.

Para añadir dependencia (blocker) tras crear las tareas:

```
mcp_asana-mcp-api_update_task(
  task_id      = "<TAREA_DEPENDIENTE_GID>",
  dependencies = ["<TAREA_BLOQUEANTE_GID>"]
)
```

---

## Ciclo de Vida de una Tarea

### TODO → IN PROGRESS

```
mcp_asana-mcp-api_add_task_to_section(task_id="<GID>", section_id="<In Progress GID>")
mcp_asana-mcp-api_create_comment(task_id="<GID>", text="Asignada a subagente. Worktree: .worktrees/<slug>")
```

### IN PROGRESS → ON HOLD (bloqueo complejo)

**Paso 1** — Crear fix task en To Do.
**Paso 2** — Registrar dependencia en la tarea original.
**Paso 3** — Mover a On Hold y comentar.
**Paso 4** — Reportar al Supervisor y DETENERSE.

### ON HOLD → IN PROGRESS (fix completada)

```
mcp_asana-mcp-api_add_task_to_section(task_id="<GID>", section_id="<In Progress GID>")
mcp_asana-mcp-api_create_comment(task_id="<GID>", text="Desbloqueada. Fix completada. Reasignada.")
```

### IN PROGRESS → DONE

```
mcp_asana-mcp-api_update_task(task_id="<GID>", completed=true)
mcp_asana-mcp-api_add_task_to_section(task_id="<GID>", section_id="<Done GID>")
mcp_asana-mcp-api_create_comment(task_id="<GID>", text="Completada. Merge commit: <SHA>")
```

---

## Consultas de Estado

```
mcp_asana-mcp-api_list_tasks(project_id="1213839935179235")
mcp_asana-mcp-api_list_tasks(project_id="1213839935179235", section_id="<GID>")
mcp_asana-mcp-api_get_task(task_id="<GID>")
```

---

## Frontera de Ejecución (Ready Frontier)

1. Listar tareas en `To Do` y `On Hold`.
2. Para cada tarea, verificar con `get_task` si todas sus dependencias están en `Done`.
3. Tareas con todas las dependencias en Done = frontera lista para despachar.
4. Frontera vacía con pendientes → revisar bloqueos o dependencias circulares.

---

## Plantilla DoD — Go

```
## Descripción
<qué debe implementar el subagente en el backend Go>

## Archivos esperados
- services/backend_go/internal/<pkg>/<file>.go
- services/backend_go/internal/<pkg>/<file>_test.go

## Definition of Done
- [ ] `go vet ./...` sin errores
- [ ] `go test ./...` — todos los tests en verde
- [ ] `go build ./...` compila sin errores
- [ ] E2E (`go test ./e2e/...`) si el cambio afecta endpoints o pipeline
- [ ] Sin regresiones en tests existentes
- [ ] Código revisado por Supervisor e integrado en develop
- [ ] Tarea movida a Done en Asana

## Fase
<nombre de la fase según ROADMAP.md>

## Depende de
<GIDs de tareas anteriores o "ninguna">
```

---

## Plantilla DoD — Expo

```
## Descripción
<qué debe implementar el subagente en la app Expo>

## Archivos esperados
- apps/expo_app/src/<ruta>.tsx
- apps/expo_app/__tests__/<test>.tsx

## Definition of Done
- [ ] `npx expo lint` sin errores
- [ ] `npx jest` — todos los tests en verde
- [ ] `npx expo export -p web` genera build limpio
- [ ] E2E (Maestro) si el cambio afecta flujo visible
- [ ] Sin regresiones en tests existentes
- [ ] Código revisado por Supervisor e integrado en develop
- [ ] Tarea movida a Done en Asana

## Fase
<nombre de la fase según ROADMAP.md>

## Depende de
<GIDs de tareas anteriores o "ninguna">
```
