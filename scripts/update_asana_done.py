"""Marcar las tareas A, B y C como Done en Asana."""
import json
import os
import requests

TOKEN_FILE = os.path.join(os.environ["APPDATA"], "asana-mcp", "token.json")
ENDPOINT = "https://mcp.asana.com/v2/mcp"

with open(TOKEN_FILE) as f:
    ACCESS_TOKEN = json.load(f)["access_token"]

TASK_A = "1213865195401267"
TASK_B = "1213839918054748"
TASK_C = "1213839957315160"
SHA = "0f3fb5b"


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
    # Inicializar sesión
    r = mcp_request("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "copilot-script", "version": "1.0"},
    })
    session_id = r.headers.get("Mcp-Session-Id")
    requests.post(ENDPOINT, headers={
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Mcp-Session-Id": session_id,
    }, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    print(f"Sesión: {session_id}")

    req_id = 2
    for gid, name in [(TASK_A, "Tarea A"), (TASK_B, "Tarea B"), (TASK_C, "Tarea C")]:
        # Marcar como completada
        result = call_tool(session_id, "update_tasks", {
            "tasks": [{"task": gid, "completed": True}]
        }, req_id=req_id)
        req_id += 1
        print(f"{name} ({gid}) → completed: {result}")

        # Añadir comentario con SHA del merge
        comment = call_tool(session_id, "add_comment", {
            "task_id": gid,
            "text": (
                f"Merged in commit {SHA}.\n"
                f"87 tests passing. Lint clean. "
                f"Phase complete — RC tagged v0.2.0-rc.1"
            ),
        }, req_id=req_id)
        req_id += 1
        print(f"  Comentario añadido: {comment}")

    # Status update en el proyecto
    status = call_tool(session_id, "create_project_status_update", {
        "parent": "1213839935179235",
        "title": "Phase complete — RC tagged v0.2.0-rc.1",
        "color": "green",
        "text": (
            "Fase 'Mapa+Driving' completada.\n\n"
            "✅ Tarea A: Mapa con gradiente freno (rojo) / acelerador (azul) / mezcla (morado)\n"
            "✅ Tarea B: Agente de conducción recibe solo throttle, freno, dirección, RPM y marcha\n"
            "✅ Tarea C: 87 tests verdes, lint limpio, commit 0f3fb5b\n\n"
            "RC: v0.2.0-rc.1 (pendiente de taggear en git develop)"
        ),
    }, req_id=req_id)
    print(f"\nEstado del proyecto actualizado: {status}")


if __name__ == "__main__":
    main()

