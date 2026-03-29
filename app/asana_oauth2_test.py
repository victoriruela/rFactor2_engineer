"""
Asana OAuth2 Flow + MCP API Test Script

Handles:
  1. Full OAuth2 authorization code flow (browser → paste redirect → exchange token)
  2. Token persistence (asana_token.json) with auto-refresh
  3. MCP endpoint tests via JSON-RPC (initialize, tools/list, tools/call)

Note: The OAuth2 app (CLIENT_ID) is registered as an MCP app, so the token
audience is "mcp-service". It only works against https://mcp.asana.com/v2/mcp,
NOT the regular Asana REST API (app.asana.com/api/1.0).
"""

import json
import os
import sys
import time
import uuid
import webbrowser
from urllib.parse import urlencode, urlparse, parse_qs, unquote

import requests

# ── Config ───────────────────────────────────────────────────────────────────
CLIENT_ID = "1213839429134637"
CLIENT_SECRET = "1d044da84c9df73466731c81befa9be9"
REDIRECT_URI = "https://localhost/"
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "..", "asana_token.json")

OAUTH_AUTHORIZE_URL = "https://app.asana.com/-/oauth_authorize"
OAUTH_TOKEN_URL = "https://app.asana.com/-/oauth_token"
MCP_ENDPOINT = "https://mcp.asana.com/v2/mcp"


# ── Token persistence ────────────────────────────────────────────────────────

def save_token(data: dict):
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Token saved to {TOKEN_FILE}")


def load_token() -> dict | None:
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)


def is_token_valid(token_data: dict | None) -> bool:
    if not token_data or "access_token" not in token_data:
        return False
    obtained_at = token_data.get("obtained_at", 0)
    expires_in = token_data.get("expires_in", 0)
    return time.time() < (obtained_at + expires_in - 120)  # 2 min safety margin


# ── OAuth2 flows ──────────────────────────────────────────────────────────────

def authorize_interactive() -> str:
    """Open browser for consent, return the authorization code."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "state": "asana_test",
    }
    url = f"{OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
    print(f"\n  Opening browser for authorization…")
    print(f"  URL: {url}\n")
    webbrowser.open(url)

    raw = input("  Paste the redirect URL (or just the 'code' value): ").strip()
    if raw.startswith("http"):
        parsed = urlparse(raw)
        codes = parse_qs(parsed.query).get("code")
        if not codes:
            raise RuntimeError("Could not extract 'code' parameter from URL.")
        return unquote(codes[0])
    return unquote(raw)


def exchange_code(code: str) -> dict:
    """Exchange authorization code for access + refresh tokens."""
    resp = requests.post(OAUTH_TOKEN_URL, data={
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code,
    })
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    data["obtained_at"] = int(time.time())
    save_token(data)
    return data


def refresh_access_token(refresh_tok: str) -> dict:
    """Use refresh token to get a new access token."""
    resp = requests.post(OAUTH_TOKEN_URL, data={
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_tok,
    })
    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    data["obtained_at"] = int(time.time())
    save_token(data)
    return data


def ensure_valid_token() -> str:
    """Return a valid access_token, refreshing or re-authorizing as needed."""
    token_data = load_token()

    # 1. Already valid
    if is_token_valid(token_data):
        print("  Existing token is still valid.")
        return token_data["access_token"]

    # 2. Try refresh
    if token_data and token_data.get("refresh_token"):
        print("  Token expired – attempting refresh…")
        try:
            token_data = refresh_access_token(token_data["refresh_token"])
            print("  Token refreshed successfully.")
            return token_data["access_token"]
        except RuntimeError as e:
            print(f"  Refresh failed: {e}")

    # 3. Full re-authorization
    print("  Starting full OAuth2 authorization flow…")
    code = authorize_interactive()
    token_data = exchange_code(code)
    print("  Token obtained successfully.")
    return token_data["access_token"]


# ── MCP JSON-RPC helpers ──────────────────────────────────────────────────────

def mcp_request(access_token: str, method: str, params: dict | None = None,
                session_id: str | None = None, request_id: int = 1) -> requests.Response:
    """Send a JSON-RPC 2.0 request to the Asana MCP endpoint."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
    }
    if params is not None:
        payload["params"] = params

    resp = requests.post(MCP_ENDPOINT, headers=headers, json=payload)
    return resp


def parse_mcp_response(resp: requests.Response) -> dict | None:
    """Parse JSON-RPC response, handling both plain JSON and SSE formats."""
    content_type = resp.headers.get("Content-Type", "")

    if resp.status_code not in (200, 202):
        print(f"  ✗ HTTP {resp.status_code}")
        print(f"    {resp.text[:500]}")
        return None

    # Plain JSON response
    if "application/json" in content_type:
        return resp.json()

    # SSE (text/event-stream) — extract JSON from data: lines
    if "text/event-stream" in content_type:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                data_str = line[len("data:"):].strip()
                if data_str:
                    try:
                        return json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
        print(f"  ✗ SSE response but no parseable JSON-RPC data")
        print(f"    Raw: {resp.text[:500]}")
        return None

    # Fallback: try JSON anyway
    try:
        return resp.json()
    except Exception:
        print(f"  ✗ Unknown content-type: {content_type}")
        print(f"    {resp.text[:500]}")
        return None


# ── MCP smoke tests ───────────────────────────────────────────────────────────

def run_mcp_tests(access_token: str):
    print("\n── MCP Endpoint Tests ──────────────────────────────")
    print(f"  Endpoint: {MCP_ENDPOINT}")

    # Step 1: initialize
    print("\n1. initialize (MCP handshake)")
    resp = mcp_request(access_token, "initialize", params={
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "asana-oauth2-test", "version": "1.0.0"},
    })
    session_id = resp.headers.get("Mcp-Session-Id")
    result = parse_mcp_response(resp)

    if not result:
        print("   ✗ initialize failed. Aborting.")
        return

    if "error" in result:
        print(f"   ✗ JSON-RPC error: {result['error']}")
        return

    server_info = result.get("result", {}).get("serverInfo", {})
    protocol = result.get("result", {}).get("protocolVersion", "?")
    print(f"   ✓ Server: {server_info.get('name', '?')} v{server_info.get('version', '?')}")
    print(f"     Protocol: {protocol}")
    if session_id:
        print(f"     Session ID: {session_id}")

    # Step 1b: send initialized notification
    print("\n2. initialized (notification)")
    notif_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        notif_headers["Mcp-Session-Id"] = session_id
    notif_payload = {"jsonrpc": "2.0", "method": "notifications/initialized"}
    notif_resp = requests.post(MCP_ENDPOINT, headers=notif_headers, json=notif_payload)
    print(f"   → HTTP {notif_resp.status_code}")

    # Step 2: tools/list
    print("\n3. tools/list")
    resp = mcp_request(access_token, "tools/list", session_id=session_id, request_id=2)
    result = parse_mcp_response(resp)
    if result and "result" in result:
        tools = result["result"].get("tools", [])
        print(f"   ✓ {len(tools)} tool(s) available:")
        for t in tools[:15]:  # show first 15
            desc = (t.get("description") or "")[:60]
            print(f"     - {t['name']}: {desc}")
        if len(tools) > 15:
            print(f"     … and {len(tools) - 15} more")
    elif result and "error" in result:
        print(f"   ✗ {result['error']}")
    else:
        print("   ✗ No result")

    # Step 3: try calling a simple tool (get_me / search)
    print("\n4. tools/call → get_me")
    resp = mcp_request(access_token, "tools/call", params={
        "name": "get_me",
        "arguments": {},
    }, session_id=session_id, request_id=3)
    result = parse_mcp_response(resp)
    if result and "result" in result:
        content = result["result"].get("content", [])
        for item in content:
            if item.get("type") == "text":
                # Try to parse and pretty-print if it's JSON
                try:
                    data = json.loads(item["text"])
                    # Asana may nest under "data" key or return flat
                    user = data.get("data", data)
                    print(f"   ✓ User info:")
                    print(json.dumps(user, indent=6, ensure_ascii=False)[:500])
                except (json.JSONDecodeError, TypeError):
                    print(f"   ✓ Response: {item['text'][:500]}")
    elif result and "error" in result:
        print(f"   ✗ {result['error']}")
    else:
        print("   ✗ No result")

    print("\n── Done ────────────────────────────────────────────\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 55)
    print("  Asana OAuth2 + API Test")
    print("=" * 55)

    if "--reauth" in sys.argv:
        print("\n  --reauth flag: forcing full re-authorization")
        code = authorize_interactive()
        token_data = exchange_code(code)
        access_token = token_data["access_token"]
    else:
        access_token = ensure_valid_token()

    run_mcp_tests(access_token)


if __name__ == "__main__":
    main()
