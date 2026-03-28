import json
import os
import requests
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs, unquote
import uuid

# Configuración
CLIENT_ID = "1213839429134637"
CLIENT_SECRET = "1d044da84c9df73466731c81befa9be9"
REDIRECT_URI = "https://localhost/"
AUTH_URL = "https://app.asana.com/-/oauth_authorize"
TOKEN_URL = "https://app.asana.com/-/oauth_token"
MCP_JSON_PATH = os.path.expandvars(r"%USERPROFILE%/AppData/Local/github-copilot/intellij/mcp.json")

# Paso 1: Obtener el código de autorización
def get_authorization_code():
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": "123"
    }
    url = f"{AUTH_URL}?{urlencode(params)}"
    print(f"Abre esta URL en tu navegador y autoriza la app:\n{url}")
    webbrowser.open(url)
    raw = input("\nPega aquí el 'code' (o la URL completa de redirección): ").strip()
    # Si el usuario pegó la URL completa, extraer el parámetro 'code'
    try:
        if raw.startswith('http'):
            parsed = urlparse(raw)
            code = parse_qs(parsed.query).get('code', [None])[0]
        else:
            # Puede ser un código URL-encoded (con %2F etc.) o el código limpio
            code = unquote(raw)
    except Exception:
        code = raw
    if not code:
        raise RuntimeError("No se pudo extraer el parámetro 'code'. Asegúrate de pegar la URL completa o el código.")
    return code

# Paso 2: Intercambiar el código por un access_token
def get_access_token(auth_code):
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": auth_code
    }
    response = requests.post(TOKEN_URL, data=data)
    # Si hay un error, mostrar body para diagnóstico (por ejemplo redirect_uri mismatch)
    if response.status_code != 200:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise RuntimeError(f"Error al obtener token (status={response.status_code}): {err}")
    return response.json()

# Paso 3: Actualizar mcp.json con el nuevo access_token
def update_mcp_json(access_token):
    with open(MCP_JSON_PATH, "r", encoding="utf-8") as f:
        mcp = json.load(f)
    # Asegura la URL correcta (usar el endpoint v2 publicado en la documentación)
    mcp["servers"]["asana-mcp"]["url"] = "https://mcp.asana.com/v2/mcp"
    if "requestInit" not in mcp["servers"]["asana-mcp"]:
        mcp["servers"]["asana-mcp"]["requestInit"] = {"headers": {}}
    if "headers" not in mcp["servers"]["asana-mcp"]["requestInit"]:
        mcp["servers"]["asana-mcp"]["requestInit"]["headers"] = {}
    headers = mcp["servers"]["asana-mcp"]["requestInit"]["headers"]
    headers["Authorization"] = f"Bearer {access_token}"
    # Asana MCP v2 requiere que el cliente acepte application/json y text/event-stream
    headers.setdefault("Accept", "application/json, text/event-stream")
    # NO escribimos un Mcp-Session-Id fijo en mcp.json:
    # El servidor MCP espera que el cliente presente un Mcp-Session-Id por conexión
    # (UUID v4). Ese valor debe generarse en tiempo de ejecución por el cliente
    # al iniciar la conexión y no persistirse en el archivo de configuración,
    # para evitar usar un session id ya caducado o inexistente en el lado del servidor.
    # Si necesitas depurar, los scripts de prueba en app/ generan un Mcp-Session-Id
    # automáticamente y lo envían en la cabecera.
    with open(MCP_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(mcp, f, indent=4)
    print("mcp.json actualizado correctamente.")

if __name__ == "__main__":
    print("=== Asana MCP OAuth2 Token Updater ===")
    code = get_authorization_code()
    try:
        token_data = get_access_token(code)
    except Exception as e:
        print(f"Error durante intercambio de código: {e}")
        raise
    # Mostrar token_data para diagnóstico (no lo hagas público)
    print("\nToken response:")
    print(json.dumps(token_data, indent=4))
    access_token = token_data.get("access_token")
    if not access_token:
        print("No se obtuvo access_token en la respuesta; revisa el JSON arriba.")
    else:
        update_mcp_json(access_token)
        print("\nToken actualizado. Puedes iniciar el servidor MCP.")

