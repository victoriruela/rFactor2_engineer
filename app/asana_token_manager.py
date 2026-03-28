import os
import json
import time
import requests
from urllib.parse import urlencode, urlparse, parse_qs

# Configuración de la app Asana
CLIENT_ID = "1213839429134637"
CLIENT_SECRET = "1d044da84c9df73466731c81befa9be9"
REDIRECT_URI = "https://localhost/"
TOKEN_FILE = "asana_token.json"
MCP_CONFIG_FILE = os.path.expandvars(r"%USERPROFILE%\\AppData\\Local\\github-copilot\\intellij\\mcp.json")

OAUTH_AUTHORIZE_URL = "https://app.asana.com/-/oauth_authorize"
OAUTH_TOKEN_URL = "https://app.asana.com/-/oauth_token"


def save_token(data):
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f)

def load_token():
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

def update_mcp_config(access_token):
    with open(MCP_CONFIG_FILE, "r") as f:
        config = json.load(f)
    # Asegura que la URL use el endpoint v2 y actualiza Authorization
    config["servers"]["asana-mcp"]["url"] = "https://mcp.asana.com/v2/mcp"
    if "requestInit" not in config["servers"]["asana-mcp"]:
        config["servers"]["asana-mcp"]["requestInit"] = {"headers": {}}
    if "headers" not in config["servers"]["asana-mcp"]["requestInit"]:
        config["servers"]["asana-mcp"]["requestInit"]["headers"] = {}
    headers = config["servers"]["asana-mcp"]["requestInit"]["headers"]
    headers["Authorization"] = f"Bearer {access_token}"
    headers.setdefault("Accept", "application/json, text/event-stream")
    # Añadir Mcp-Session-Id si no existe
    import uuid
    headers.setdefault("Mcp-Session-Id", str(uuid.uuid4()))
    with open(MCP_CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)

def get_new_token_with_code(auth_code):
    data = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": auth_code
    }
    response = requests.post(OAUTH_TOKEN_URL, data=data)
    if response.status_code != 200:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise RuntimeError(f"Error al intercambiar código (status={response.status_code}): {err}")
    token_data = response.json()
    token_data["obtained_at"] = int(time.time())
    save_token(token_data)
    update_mcp_config(token_data["access_token"])
    return token_data

def refresh_token(refresh_token):
    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "refresh_token": refresh_token
    }
    response = requests.post(OAUTH_TOKEN_URL, data=data)
    if response.status_code != 200:
        try:
            err = response.json()
        except Exception:
            err = response.text
        raise RuntimeError(f"Error al refrescar token (status={response.status_code}): {err}")
    token_data = response.json()
    token_data["obtained_at"] = int(time.time())
    save_token(token_data)
    update_mcp_config(token_data["access_token"])
    return token_data

def is_token_valid(token_data):
    if not token_data:
        return False
    expires_in = token_data.get("expires_in", 0)
    obtained_at = token_data.get("obtained_at", 0)
    return (int(time.time()) < obtained_at + expires_in - 60)  # 60s margen

def main():
    token_data = load_token()
    if is_token_valid(token_data):
        update_mcp_config(token_data["access_token"])
        print("Token válido. Listo para usar.")
        return
    if token_data and "refresh_token" in token_data:
        print("Token caducado. Renovando con refresh_token...")
        try:
            token_data = refresh_token(token_data["refresh_token"])
            print("Token renovado correctamente.")
            return
        except Exception as e:
            print(f"Error al renovar token: {e}")
    # Si no hay refresh_token o falla, pedir code manualmente
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": "123"
    }
    url = f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
    print("Por favor, abre esta URL en tu navegador y autoriza la app:")
    print(url)
    auth_url = input("Pega aquí la URL de redirección completa: ")
    # Extraer el parámetro code de la URL
    try:
        parsed = urlparse(auth_url.strip())
        code = parse_qs(parsed.query)["code"][0]
    except Exception:
        print("No se pudo extraer el parámetro 'code' de la URL. Asegúrate de pegar la URL completa de redirección.")
        return
    token_data = get_new_token_with_code(code)
    print("Token obtenido y guardado correctamente.")

if __name__ == "__main__":
    main()
