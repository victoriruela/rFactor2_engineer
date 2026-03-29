#!/usr/bin/env python3
"""
Asana MCP CLI — OAuth2 authentication, token management, and mcp.json configuration.

Subcommands:
  setup       Interactive first-time setup (creates config.json)
  auth        Ensure valid token (refresh or full OAuth2 flow)
  update-mcp  Write current token into Copilot's mcp.json
  test        Run MCP smoke tests (initialize, tools/list, get_me)
  status      Show token validity, config paths, mcp.json status

The OAuth2 app is registered as an MCP app (aud: "mcp-service").
Tokens only work against https://mcp.asana.com/v2/mcp, NOT the REST API.
"""

import argparse
import json
import os
import platform
import stat
import sys
import time
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs, unquote

try:
    import requests
except ImportError:
    print("Error: 'requests' is required.  Install it with:")
    print("  pip install requests")
    sys.exit(1)


# ── Defaults ─────────────────────────────────────────────────────────────────

DEFAULTS = {
    "client_id": "1213839429134637",
    "client_secret": "1d044da84c9df73466731c81befa9be9",
    "redirect_uri": "https://localhost/",
    "mcp_endpoint": "https://mcp.asana.com/v2/mcp",
    "oauth_authorize_url": "https://app.asana.com/-/oauth_authorize",
    "oauth_token_url": "https://app.asana.com/-/oauth_token",
}

ENV_MAP = {
    "ASANA_CLIENT_ID": "client_id",
    "ASANA_CLIENT_SECRET": "client_secret",
    "ASANA_REDIRECT_URI": "redirect_uri",
    "ASANA_MCP_ENDPOINT": "mcp_endpoint",
    "ASANA_TOKEN_FILE": "token_file",
}


# ── Platform helpers ─────────────────────────────────────────────────────────

def get_config_dir() -> Path:
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
        return Path(base) / "asana-mcp"
    elif system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "asana-mcp"
    else:
        base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
        return Path(base) / "asana-mcp"


def get_ide_targets() -> dict[str, dict]:
    """Return all known IDE MCP config paths and their formats.

    Each target has:
      path:   absolute path to the config file
      format: 'copilot-vscode' | 'copilot-jetbrains' | 'claude-desktop' | 'claude-cli'
    """
    system = platform.system()
    home = Path.home()
    targets = {}

    if system == "Windows":
        local = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        targets["copilot-jetbrains"] = {
            "path": str(local / "github-copilot" / "intellij" / "mcp.json"),
            "format": "copilot-jetbrains",
        }
        targets["copilot-vscode"] = {
            "path": str(appdata / "Code" / "User" / "mcp.json"),
            "format": "copilot-vscode",
        }
        targets["claude-desktop"] = {
            "path": str(appdata / "Claude" / "claude_desktop_config.json"),
            "format": "claude-desktop",
        }
        targets["claude-cli"] = {
            "path": str(home / ".claude.json"),
            "format": "claude-cli",
        }
    elif system == "Darwin":
        app_support = home / "Library" / "Application Support"
        targets["copilot-jetbrains"] = {
            "path": str(app_support / "github-copilot" / "intellij" / "mcp.json"),
            "format": "copilot-jetbrains",
        }
        targets["copilot-vscode"] = {
            "path": str(app_support / "Code" / "User" / "mcp.json"),
            "format": "copilot-vscode",
        }
        targets["claude-desktop"] = {
            "path": str(app_support / "Claude" / "claude_desktop_config.json"),
            "format": "claude-desktop",
        }
        targets["claude-cli"] = {
            "path": str(home / ".claude.json"),
            "format": "claude-cli",
        }
    else:  # Linux
        xdg = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))
        targets["copilot-jetbrains"] = {
            "path": str(xdg / "github-copilot" / "intellij" / "mcp.json"),
            "format": "copilot-jetbrains",
        }
        targets["copilot-vscode"] = {
            "path": str(xdg / "Code" / "User" / "mcp.json"),
            "format": "copilot-vscode",
        }
        targets["claude-desktop"] = {
            "path": str(xdg / "Claude" / "claude_desktop_config.json"),
            "format": "claude-desktop",
        }
        targets["claude-cli"] = {
            "path": str(home / ".claude.json"),
            "format": "claude-cli",
        }

    return targets


IDE_TARGET_NAMES = ["copilot-jetbrains", "copilot-vscode", "claude-desktop", "claude-cli"]


# ── Config resolution ────────────────────────────────────────────────────────

def load_config() -> dict:
    """Merge: defaults → user config → project config → env vars."""
    cfg = dict(DEFAULTS)
    config_dir = get_config_dir()
    cfg["token_file"] = str(config_dir / "token.json")

    # User config
    user_cfg_path = config_dir / "config.json"
    if user_cfg_path.exists():
        with open(user_cfg_path, "r") as f:
            user_cfg = json.load(f)
        cfg.update({k: v for k, v in user_cfg.items() if v})

    # Project config (.asana-mcp.json in cwd)
    project_cfg_path = Path.cwd() / ".asana-mcp.json"
    if project_cfg_path.exists():
        with open(project_cfg_path, "r") as f:
            project_cfg = json.load(f)
        cfg.update({k: v for k, v in project_cfg.items() if v})

    # Environment variables (highest priority)
    for env_key, cfg_key in ENV_MAP.items():
        val = os.environ.get(env_key)
        if val:
            cfg[cfg_key] = val

    return cfg


def save_config(cfg_data: dict):
    """Write user config to ~/.config/asana-mcp/config.json with restricted perms."""
    config_dir = get_config_dir()
    config_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = config_dir / "config.json"
    with open(cfg_path, "w") as f:
        json.dump(cfg_data, f, indent=2)
    # Restrict permissions (owner-only) on non-Windows
    if platform.system() != "Windows":
        cfg_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"  Config saved to {cfg_path}")


# ── Token persistence ────────────────────────────────────────────────────────

def load_token(cfg: dict) -> dict | None:
    token_path = Path(cfg["token_file"])
    if not token_path.exists():
        return None
    with open(token_path, "r") as f:
        return json.load(f)


def save_token(cfg: dict, data: dict):
    token_path = Path(cfg["token_file"])
    token_path.parent.mkdir(parents=True, exist_ok=True)
    with open(token_path, "w") as f:
        json.dump(data, f, indent=2)
    if platform.system() != "Windows":
        token_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    print(f"  Token saved to {token_path}")


def is_token_valid(token_data: dict | None) -> bool:
    if not token_data or "access_token" not in token_data:
        return False
    obtained_at = token_data.get("obtained_at", 0)
    expires_in = token_data.get("expires_in", 0)
    return time.time() < (obtained_at + expires_in - 120)


def token_expires_in(token_data: dict | None) -> str:
    if not token_data or "obtained_at" not in token_data:
        return "unknown"
    remaining = (token_data["obtained_at"] + token_data.get("expires_in", 0)) - time.time()
    if remaining <= 0:
        return "expired"
    mins = int(remaining // 60)
    secs = int(remaining % 60)
    return f"{mins}m {secs}s"


# ── OAuth2 flows ─────────────────────────────────────────────────────────────

def authorize_interactive(cfg: dict) -> str:
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "response_type": "code",
        "state": "asana_mcp",
    }
    url = f"{cfg['oauth_authorize_url']}?{urlencode(params)}"
    print(f"\n  Opening browser for authorization...")
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


def exchange_code(cfg: dict, code: str) -> dict:
    resp = requests.post(cfg["oauth_token_url"], data={
        "grant_type": "authorization_code",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "redirect_uri": cfg["redirect_uri"],
        "code": code,
    })
    if resp.status_code != 200:
        raise RuntimeError(f"Token exchange failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    data["obtained_at"] = int(time.time())
    save_token(cfg, data)
    return data


def refresh_access_token(cfg: dict, refresh_tok: str) -> dict:
    resp = requests.post(cfg["oauth_token_url"], data={
        "grant_type": "refresh_token",
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "refresh_token": refresh_tok,
    })
    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed ({resp.status_code}): {resp.text}")
    data = resp.json()
    data["obtained_at"] = int(time.time())
    save_token(cfg, data)
    return data


def ensure_valid_token(cfg: dict, force: bool = False) -> str:
    if not force:
        token_data = load_token(cfg)
        if is_token_valid(token_data):
            print(f"  Existing token is still valid ({token_expires_in(token_data)} remaining).")
            return token_data["access_token"]
        if token_data and token_data.get("refresh_token"):
            print("  Token expired - attempting refresh...")
            try:
                token_data = refresh_access_token(cfg, token_data["refresh_token"])
                print("  Token refreshed successfully.")
                return token_data["access_token"]
            except RuntimeError as e:
                print(f"  Refresh failed: {e}")

    print("  Starting full OAuth2 authorization flow...")
    code = authorize_interactive(cfg)
    token_data = exchange_code(cfg, code)
    print("  Token obtained successfully.")
    return token_data["access_token"]


# ── mcp.json updater ─────────────────────────────────────────────────────────

def _read_or_init(path: str) -> dict:
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _write_config(path: str, config: dict):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)


def _apply_copilot_jetbrains(config: dict, endpoint: str, token: str) -> dict:
    """Copilot IntelliJ: servers.asana-mcp.requestInit.headers format."""
    server = config.setdefault("servers", {}).setdefault("asana-mcp", {})
    server["url"] = endpoint
    req_init = server.setdefault("requestInit", {})
    headers = req_init.setdefault("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    headers["Accept"] = "application/json, text/event-stream"
    headers.pop("Mcp-Session-Id", None)
    return config


def _apply_copilot_vscode(config: dict, endpoint: str, token: str) -> dict:
    """Copilot VS Code: servers.asana-mcp with type/url/headers at top level."""
    server = config.setdefault("servers", {}).setdefault("asana-mcp", {})
    server["type"] = "http"
    server["url"] = endpoint
    server["headers"] = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }
    server.pop("requestInit", None)
    server.pop("Mcp-Session-Id", None)
    return config


def _apply_claude_desktop(config: dict, endpoint: str, token: str) -> dict:
    """Claude Desktop: mcpServers.asana-mcp with type/url/headers."""
    server = config.setdefault("mcpServers", {}).setdefault("asana-mcp", {})
    server["type"] = "http"
    server["url"] = endpoint
    server["headers"] = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }
    return config


def _apply_claude_cli(config: dict, endpoint: str, token: str) -> dict:
    """Claude CLI (~/.claude.json): mcpServers.asana-mcp with type/url/headers."""
    server = config.setdefault("mcpServers", {}).setdefault("asana-mcp", {})
    server["type"] = "http"
    server["url"] = endpoint
    server["headers"] = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }
    return config


FORMAT_APPLIERS = {
    "copilot-jetbrains": _apply_copilot_jetbrains,
    "copilot-vscode": _apply_copilot_vscode,
    "claude-desktop": _apply_claude_desktop,
    "claude-cli": _apply_claude_cli,
}


def update_mcp_for_target(cfg: dict, access_token: str, target_name: str,
                          path_override: str | None = None):
    targets = get_ide_targets()
    target = targets.get(target_name)
    if not target:
        print(f"  x Unknown target: {target_name}")
        return

    mcp_path = path_override or target["path"]
    fmt = target["format"]
    applier = FORMAT_APPLIERS[fmt]

    config = _read_or_init(mcp_path)
    config = applier(config, cfg["mcp_endpoint"], access_token)
    _write_config(mcp_path, config)
    print(f"  OK [{target_name}] {mcp_path}")


# ── MCP JSON-RPC helpers ───────────────────────────────────────��─────────────

def mcp_request(cfg: dict, access_token: str, method: str,
                params: dict | None = None, session_id: str | None = None,
                request_id: int = 1) -> requests.Response:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        headers["Mcp-Session-Id"] = session_id

    payload = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        payload["params"] = params

    return requests.post(cfg["mcp_endpoint"], headers=headers, json=payload)


def parse_mcp_response(resp: requests.Response) -> dict | None:
    content_type = resp.headers.get("Content-Type", "")

    if resp.status_code not in (200, 202):
        print(f"  x HTTP {resp.status_code}")
        print(f"    {resp.text[:500]}")
        return None

    if "application/json" in content_type:
        return resp.json()

    if "text/event-stream" in content_type:
        for line in resp.text.splitlines():
            if line.startswith("data:"):
                data_str = line[len("data:"):].strip()
                if data_str:
                    try:
                        return json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
        print(f"  x SSE response but no parseable JSON-RPC data")
        print(f"    Raw: {resp.text[:500]}")
        return None

    try:
        return resp.json()
    except Exception:
        print(f"  x Unknown content-type: {content_type}")
        print(f"    {resp.text[:500]}")
        return None


# ── Subcommands ──────────────────────────────────────────────────────────────

def cmd_setup(args):
    """Interactive first-time setup."""
    print("=" * 55)
    print("  Asana MCP - Setup")
    print("=" * 55)

    config_dir = get_config_dir()
    cfg_path = config_dir / "config.json"
    existing = {}
    if cfg_path.exists():
        with open(cfg_path, "r") as f:
            existing = json.load(f)
        print(f"\n  Existing config found at {cfg_path}")
        print("  Press Enter to keep current values.\n")

    def prompt(label, key, default):
        current = existing.get(key, default)
        val = input(f"  {label} [{current}]: ").strip()
        return val if val else current

    new_cfg = {
        "client_id": prompt("Client ID", "client_id", DEFAULTS["client_id"]),
        "client_secret": prompt("Client Secret", "client_secret", DEFAULTS["client_secret"]),
        "redirect_uri": prompt("Redirect URI", "redirect_uri", DEFAULTS["redirect_uri"]),
        "mcp_endpoint": prompt("MCP Endpoint", "mcp_endpoint", DEFAULTS["mcp_endpoint"]),
    }

    default_mcp_path = get_default_mcp_json_path()
    custom_mcp = input(f"\n  Copilot mcp.json path [{default_mcp_path}]: ").strip()
    if custom_mcp:
        new_cfg["mcp_json_path"] = custom_mcp

    save_config(new_cfg)
    print("\n  Setup complete. Run 'auth' next to authenticate.")


def cmd_auth(args):
    """Ensure valid token."""
    print("=" * 55)
    print("  Asana MCP - Authenticate")
    print("=" * 55)

    cfg = load_config()
    access_token = ensure_valid_token(cfg, force=args.force)
    print(f"\n  Access token: {access_token[:20]}...{access_token[-10:]}")


def cmd_update_mcp(args):
    """Write token into IDE MCP config files."""
    print("=" * 55)
    print("  Asana MCP - Update IDE Configs")
    print("=" * 55)

    cfg = load_config()
    token_data = load_token(cfg)

    if not is_token_valid(token_data):
        print("  Token is expired or missing. Running auth first...")
        access_token = ensure_valid_token(cfg)
    else:
        access_token = token_data["access_token"]

    targets = get_ide_targets()

    if args.path:
        # Manual path override — use the format of the specified target (or jetbrains default)
        target_name = args.target[0] if args.target else "copilot-jetbrains"
        print(f"\n  Writing to custom path as [{target_name}] format:")
        update_mcp_for_target(cfg, access_token, target_name, path_override=args.path)
        return

    if args.all:
        target_names = IDE_TARGET_NAMES
    elif args.target:
        target_names = args.target
    else:
        # Default: detect which config files already exist
        existing = [name for name, t in targets.items() if os.path.exists(t["path"])]
        if existing:
            target_names = existing
            print(f"\n  Auto-detected {len(existing)} existing config(s):")
        else:
            print("\n  No existing IDE configs found. Available targets:")
            for name, t in targets.items():
                print(f"    {name:20s} {t['path']}")
            print("\n  Use --target <name> or --all to create one.")
            return

    print()
    for name in target_names:
        update_mcp_for_target(cfg, access_token, name)


def cmd_test(args):
    """Run MCP smoke tests."""
    print("=" * 55)
    print("  Asana MCP - Smoke Tests")
    print("=" * 55)

    cfg = load_config()
    token_data = load_token(cfg)

    if not is_token_valid(token_data):
        print("  Token is expired or missing. Running auth first...")
        access_token = ensure_valid_token(cfg)
    else:
        access_token = token_data["access_token"]

    endpoint = cfg["mcp_endpoint"]
    print(f"\n  Endpoint: {endpoint}")

    # 1. initialize
    print("\n1. initialize (MCP handshake)")
    resp = mcp_request(cfg, access_token, "initialize", params={
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "asana-mcp-cli", "version": "1.0.0"},
    })
    session_id = resp.headers.get("Mcp-Session-Id")
    result = parse_mcp_response(resp)

    if not result:
        print("   x initialize failed. Aborting.")
        return
    if "error" in result:
        print(f"   x JSON-RPC error: {result['error']}")
        return

    server_info = result.get("result", {}).get("serverInfo", {})
    proto = result.get("result", {}).get("protocolVersion", "?")
    print(f"   OK Server: {server_info.get('name', '?')} v{server_info.get('version', '?')}")
    print(f"      Protocol: {proto}")
    if session_id:
        print(f"      Session ID: {session_id}")

    # 2. initialized notification
    print("\n2. initialized (notification)")
    notif_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if session_id:
        notif_headers["Mcp-Session-Id"] = session_id
    notif_resp = requests.post(endpoint, headers=notif_headers,
                               json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    print(f"   -> HTTP {notif_resp.status_code}")

    # 3. tools/list
    print("\n3. tools/list")
    resp = mcp_request(cfg, access_token, "tools/list",
                       session_id=session_id, request_id=2)
    result = parse_mcp_response(resp)
    if result and "result" in result:
        tools = result["result"].get("tools", [])
        print(f"   OK {len(tools)} tool(s) available:")
        for t in tools[:15]:
            desc = (t.get("description") or "")[:60]
            print(f"      - {t['name']}: {desc}")
        if len(tools) > 15:
            print(f"      ... and {len(tools) - 15} more")
    elif result and "error" in result:
        print(f"   x {result['error']}")
    else:
        print("   x No result")

    # 4. tools/call get_me
    print("\n4. tools/call -> get_me")
    resp = mcp_request(cfg, access_token, "tools/call", params={
        "name": "get_me", "arguments": {},
    }, session_id=session_id, request_id=3)
    result = parse_mcp_response(resp)
    if result and "result" in result:
        content = result["result"].get("content", [])
        for item in content:
            if item.get("type") == "text":
                try:
                    data = json.loads(item["text"])
                    user = data.get("data", data)
                    print(f"   OK User info:")
                    print(json.dumps(user, indent=6, ensure_ascii=False)[:500])
                except (json.JSONDecodeError, TypeError):
                    print(f"   OK Response: {item['text'][:500]}")
    elif result and "error" in result:
        print(f"   x {result['error']}")
    else:
        print("   x No result")

    print("\n  Done.")


def cmd_status(args):
    """Show current status: config, token, mcp.json."""
    print("=" * 55)
    print("  Asana MCP - Status")
    print("=" * 55)

    cfg = load_config()
    config_dir = get_config_dir()
    cfg_path = config_dir / "config.json"

    print(f"\n  Platform:       {platform.system()} ({platform.machine()})")
    print(f"  Config dir:     {config_dir}")
    print(f"  Config file:    {cfg_path} ({'exists' if cfg_path.exists() else 'NOT FOUND'})")
    print(f"  Token file:     {cfg['token_file']} ({'exists' if Path(cfg['token_file']).exists() else 'NOT FOUND'})")
    print(f"  MCP endpoint:   {cfg['mcp_endpoint']}")
    print(f"  Client ID:      {cfg['client_id']}")
    print(f"  Redirect URI:   {cfg['redirect_uri']}")

    # IDE targets
    targets = get_ide_targets()
    print(f"\n  IDE configs:")
    for name, t in targets.items():
        exists = os.path.exists(t["path"])
        marker = "exists" if exists else "---"
        print(f"    {name:20s} [{marker:7s}] {t['path']}")

    # Project override
    project_cfg = Path.cwd() / ".asana-mcp.json"
    if project_cfg.exists():
        print(f"\n  Project config: {project_cfg} (active)")
    else:
        print(f"\n  Project config: none (using user config only)")

    # Token status
    token_data = load_token(cfg)
    if token_data:
        valid = is_token_valid(token_data)
        remaining = token_expires_in(token_data)
        user_name = token_data.get("data", {}).get("name", "?")
        user_email = token_data.get("data", {}).get("email", "?")
        workspace = token_data.get("data", {}).get("authorized_workspace", {}).get("name", "?")
        print(f"\n  Token status:   {'VALID' if valid else 'EXPIRED'} ({remaining})")
        print(f"  User:           {user_name} ({user_email})")
        print(f"  Workspace:      {workspace}")
    else:
        print(f"\n  Token status:   NO TOKEN (run 'auth' first)")

    # Env overrides
    active_envs = {k: v for k, v in ENV_MAP.items() if os.environ.get(k)}
    if active_envs:
        print(f"\n  Env overrides:")
        for env_key, cfg_key in active_envs.items():
            print(f"    {env_key} -> {cfg_key}")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="asana_mcp",
        description="Asana MCP - OAuth2 auth, token management, mcp.json config",
    )
    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("setup", help="Interactive first-time setup")

    auth_p = sub.add_parser("auth", help="Authenticate (refresh or full OAuth2)")
    auth_p.add_argument("--force", action="store_true",
                        help="Force full re-authorization (ignore existing token)")

    mcp_p = sub.add_parser("update-mcp", help="Write token into IDE MCP configs")
    mcp_p.add_argument("--target", nargs="+", choices=IDE_TARGET_NAMES,
                        help="Specific IDE target(s). Default: auto-detect existing configs")
    mcp_p.add_argument("--all", action="store_true",
                        help="Write to all IDE targets")
    mcp_p.add_argument("--path", help="Override config file path (use with --target for format)")

    sub.add_parser("test", help="Run MCP smoke tests")
    sub.add_parser("status", help="Show config, token, and mcp.json status")

    args = parser.parse_args()

    commands = {
        "setup": cmd_setup,
        "auth": cmd_auth,
        "update-mcp": cmd_update_mcp,
        "test": cmd_test,
        "status": cmd_status,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
