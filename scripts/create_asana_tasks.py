"""
Script para crear las tareas de Asana para la fase:
  Mapa con gradiente freno/acelerador + filtro telemetría conducción
Usa el token MCP renovado.
"""
import json
import os
import requests

TOKEN_FILE = os.path.join(os.environ["APPDATA"], "asana-mcp", "token.json")
ENDPOINT = "https://mcp.asana.com/v2/mcp"

with open(TOKEN_FILE) as f:
    token_data = json.load(f)
ACCESS_TOKEN = token_data["access_token"]


def mcp_request(method, params=None, session_id=None, req_id=1):
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    payload = {"jsonrpc": "2.0", "id": req_id, "method": method}
    if params is not None:
        payload["params"] = params
    return requests.post(ENDPOINT, headers=headers, json=payload)


def parse_resp(resp):
    ct = resp.headers.get("Content-Type", "")
    if "text/event-stream" in ct:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                data_str = line[5:].strip()
                if data_str:
                    try:
                        return json.loads(data_str)
                    except Exception:
                        continue
        return None
    try:
        return resp.json()
    except Exception:
        return None


def call_tool(session_id, tool_name, arguments, req_id=1):
    r = mcp_request("tools/call", {"name": tool_name, "arguments": arguments},
                    session_id=session_id, req_id=req_id)
    result = parse_resp(r)
    if result and "result" in result:
        content = result["result"].get("content", [])
        for item in content:
            if item.get("type") == "text":
                try:
                    return json.loads(item["text"])
                except Exception:
                    return item["text"]
    if result and "error" in result:
        print(f"  ERROR: {result['error']}")
    return None


def main():
    # 1. Inicializar sesión MCP
    r = mcp_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "copilot-script", "version": "1.0"},
    })
    result = parse_resp(r)
    session_id = r.headers.get("Mcp-Session-Id")
    print(f"Session: {session_id}")

    # 2. Notification initialized
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Mcp-Session-Id": session_id,
    }
    requests.post(ENDPOINT, headers=headers,
                  json={"jsonrpc": "2.0", "method": "notifications/initialized"})

    # 3. Obtener usuario actual
    me = call_tool(session_id, "get_me", {}, req_id=2)
    print(f"Usuario: {me}")

    # 4. Buscar o usar proyecto rFactor2 Engineer ya existente
    projects = call_tool(session_id, "get_projects", {}, req_id=3)
    print(f"Proyectos: {json.dumps(projects, indent=2)[:500]}")

    existing_project = None
    if projects and "data" in projects:
        for p in projects["data"]:
            if "rfactor" in p.get("name", "").lower() or "engineer" in p.get("name", "").lower():
                existing_project = p
                break

    if existing_project:
        project_gid = existing_project["gid"]
        print(f"Proyecto encontrado: {existing_project['name']} (GID: {project_gid})")
    else:
        # Crear proyecto
        new_proj = call_tool(session_id, "create_project", {
            "name": "rFactor2 Engineer",
            "notes": "Proyecto de desarrollo de la app rFactor2 Engineer - análisis de telemetría y setup con IA.",
            "color": "dark-red",
            "default_view": "list",
        }, req_id=4)
        print(f"Proyecto creado: {json.dumps(new_proj, indent=2)[:300]}")
        # create_project devuelve el objeto directamente (sin wrapper "data")
        if isinstance(new_proj, dict) and "gid" in new_proj:
            project_gid = new_proj["gid"]
        else:
            project_gid = new_proj["data"]["gid"]

    print(f"\nUsando proyecto GID: {project_gid}")

    # 5. Crear Tarea A (sin dependencias)
    task_a_data = call_tool(session_id, "create_tasks", {
        "default_project": project_gid,
        "tasks": [
            {
                "name": "[Fase: Mapa+Driving] Tarea A: Mapa con gradiente freno/acelerador",
                "notes": (
                    "Implementar coloreado por tramos en el mapa del circuito.\n\n"
                    "Descripción:\n"
                    "- Añadir arrays `raw_lon`, `raw_lat`, `brake` (0-100%) y `throttle` (0-100%) "
                    "a `data['map']` en `_build_lap_data()` (frontend/streamlit_app.py)\n"
                    "- Reemplazar el renderizado del mapa JS: 3 trazas Plotly:\n"
                    "  * Traza 0: línea gris de fondo (circuito completo)\n"
                    "  * Traza 1: marcadores coloreados (brake=rojo, throttle=azul, ambos=mezcla morada)\n"
                    "  * Traza 2: marcador de posición del coche\n"
                    "- Gradiente: 0%=blanco, 100%=rojo pleno (#FF0000) para freno / azul pleno (#0000FF) para acelerador\n"
                    "- Si brake Y throttle activos simultáneamente: mezcla rgb(255-t, 255-b-t, 255-b) → morado\n"
                    "- Solo mostrar tramos activos (sin color para coast)\n"
                    "- Actualizar Plotly.restyle de posición del coche de traza [1] a [2]\n"
                    "- Añadir unit tests para `_build_lap_data()` en tests/\n\n"
                    "Archivos: frontend/streamlit_app.py, tests/\n"
                    "Fase: Mapa+Driving\n"
                    "Depende de: ninguna"
                ),
            }
        ],
    }, req_id=5)
    print(f"\nTarea A creada: {json.dumps(task_a_data, indent=2)[:400]}")
    task_a_gid = task_a_data["succeeded"][0]["gid"]
    print(f"Tarea A GID: {task_a_gid}")

    # 6. Crear Tarea B (sin dependencias — paralela a A)
    task_b_data = call_tool(session_id, "create_tasks", {
        "default_project": project_gid,
        "tasks": [
            {
                "name": "[Fase: Mapa+Driving] Tarea B: Filtro telemetría agente de conducción",
                "notes": (
                    "Restringir la telemetría enviada al agente de conducción a canales de técnica de pilotaje.\n\n"
                    "Descripción:\n"
                    "- En app/main.py: construir `driving_csv_for_ai` filtrado a columnas: "
                    "`Lap Number`, `Lap Distance`, `Throttle Pos`, `Brake Pos`, `Steering`, `Engine RPM`, `Gear`\n"
                    "- Construir `driving_summary` (mismo formato que `summary` pero con CSV filtrado)\n"
                    "- Pasar `driving_telemetry_summary=driving_summary` a `ai_engineer.analyze()`\n"
                    "- En app/core/ai_agents.py: añadir parámetro `driving_telemetry_summary=None` a `analyze()`\n"
                    "- Usar `driving_telemetry_summary or telemetry_summary` al invocar el DRIVING_PROMPT\n"
                    "- Actualizar tests: tests/core/test_ai_agents.py y tests/test_main.py\n\n"
                    "Archivos: app/main.py, app/core/ai_agents.py, tests/core/test_ai_agents.py, tests/test_main.py\n"
                    "Fase: Mapa+Driving\n"
                    "Depende de: ninguna"
                ),
            }
        ],
    }, req_id=6)
    print(f"\nTarea B creada: {json.dumps(task_b_data, indent=2)[:400]}")
    task_b_gid = task_b_data["succeeded"][0]["gid"]
    print(f"Tarea B GID: {task_b_gid}")

    # 7. Crear Tarea C: Validación final (depende de A y B)
    task_c_data = call_tool(session_id, "create_tasks", {
        "default_project": project_gid,
        "tasks": [
            {
                "name": "[Fase: Mapa+Driving] Tarea C: Suite de tests verde + RC tag",
                "notes": (
                    "Validación final de la fase tras merge de Tarea A y Tarea B.\n\n"
                    "Descripción:\n"
                    "- Ejecutar suite completa: `pytest tests/ --ignore=tests/integration -v`\n"
                    "- Ejecutar ruff: `python -m ruff check app/ frontend/ tests/`\n"
                    "- Corregir cualquier fallo de lint o test\n"
                    "- Taggear Release Candidate en develop: `git tag v0.X.0-rc.1`\n"
                    "- Actualizar estado del proyecto Asana: 'Phase complete — RC tagged'\n\n"
                    "Archivos: ninguno propio (solo validación)\n"
                    "Fase: Mapa+Driving\n"
                    f"Depende de: Tarea A ({task_a_gid}), Tarea B ({task_b_gid})"
                ),
            }
        ],
    }, req_id=7)
    print(f"\nTarea C creada: {json.dumps(task_c_data, indent=2)[:400]}")
    task_c_gid = task_c_data["succeeded"][0]["gid"]

    # 8. Establecer dependencias de C → A y C → B
    dep_result = call_tool(session_id, "update_tasks", {
        "tasks": [
            {
                "task": task_c_gid,
                "add_dependencies": [task_a_gid, task_b_gid],
            }
        ]
    }, req_id=8)
    print(f"\nDependencias Tarea C establecidas: {json.dumps(dep_result, indent=2)[:300]}")

    # 9. Estado inicial: A y B → In Progress (ambas en la ready frontier)
    # Añadir comentario de inicio en A y B
    comment_a = call_tool(session_id, "add_comment", {
        "task_id": task_a_gid,
        "text": "Assigned to subagent. Starting implementation of gradient map coloring.",
    }, req_id=9)
    comment_b = call_tool(session_id, "add_comment", {
        "task_id": task_b_gid,
        "text": "Assigned to subagent. Starting implementation of driving telemetry filter.",
    }, req_id=10)
    print(f"\nComentarios de inicio añadidos.")

    print("\n" + "="*60)
    print("RESUMEN DE TAREAS CREADAS:")
    print(f"  Proyecto GID : {project_gid}")
    print(f"  Tarea A GID  : {task_a_gid}  (Mapa gradiente — sin deps)")
    print(f"  Tarea B GID  : {task_b_gid}  (Filtro telemetría — sin deps)")
    print(f"  Tarea C GID  : {task_c_gid}  (Validación — depende de A+B)")
    print("="*60)


if __name__ == "__main__":
    main()



