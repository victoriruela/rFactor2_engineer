---
name: asana-mcp
description: This skill should be used when the user asks to "authenticate Asana", "refresh Asana token", "update mcp.json for Asana", "configure Asana MCP", "set up Asana integration", "Asana OAuth", "Asana token expired", "test Asana MCP connection", "check Asana status", "add Asana to Claude Desktop", "add Asana to VS Code", "add Asana to JetBrains", mentions Asana MCP tokens, or discusses Asana MCP configuration across projects or IDEs. Provides OAuth2 authentication, token lifecycle management, and multi-IDE mcp.json configuration for Asana's MCP endpoint.
version: 1.0.0
---

# Asana MCP Integration

## Overview

Manage Asana MCP OAuth2 authentication, token lifecycle, and IDE MCP configuration. The CLI script at `${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py` handles all operations cross-platform (Windows, macOS, Linux) and writes the correct config format for each IDE.

**Key constraint:** The OAuth2 app issues tokens with audience `mcp-service`. These tokens only work against `https://mcp.asana.com/v2/mcp` (MCP JSON-RPC), NOT the standard Asana REST API.

## CLI Commands

All commands run via:
```
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py <command>
```

### First-Time Setup

```
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py setup
```

Create or update the user config at the platform config directory. Prompts for client_id, client_secret, redirect_uri, mcp_endpoint, and mcp.json path. Press Enter to keep defaults.

### Authenticate

```
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py auth
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py auth --force
```

Ensure a valid access token exists:
1. If a valid token exists (not expired), reuse it
2. If expired but refresh token available, refresh silently
3. If refresh fails or no token, open browser for full OAuth2 consent

Use `--force` to skip steps 1-2 and force full re-authorization.

### Update IDE Configs

```
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py update-mcp
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py update-mcp --target copilot-vscode claude-desktop
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py update-mcp --all
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py update-mcp --path /custom/mcp.json
```

Write the current Bearer token into IDE MCP config files with the correct format per IDE.

**Supported targets:**

| Target              | Config format                                      |
|---------------------|----------------------------------------------------|
| `copilot-jetbrains` | `servers.asana-mcp.requestInit.headers` format      |
| `copilot-vscode`    | `servers.asana-mcp` with `type`/`url`/`headers`    |
| `claude-desktop`    | `mcpServers.asana-mcp` with `type`/`url`/`headers` |
| `claude-cli`        | `mcpServers.asana-mcp` with `type`/`url`/`headers` |

**Default behavior:** auto-detects which config files already exist on disk and updates only those. Use `--target` to specify, `--all` to write all, or `--path` for a custom file.

Important: Do NOT hardcode `Mcp-Session-Id` in config files. The MCP client must generate a fresh one per connection at runtime.

### Test MCP Connection

```
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py test
```

Run a full MCP smoke test:
1. `initialize` — JSON-RPC handshake, verify server name and protocol version
2. `notifications/initialized` — complete handshake
3. `tools/list` — enumerate available tools (expect ~22)
4. `tools/call get_me` — verify authenticated access, show user info

### Check Status

```
python ${CLAUDE_PLUGIN_ROOT}/scripts/asana_mcp.py status
```

Show all configuration state: platform, config paths, token validity (with remaining time), authenticated user, workspace, active project overrides, and env var overrides.

## Config Hierarchy

Configuration resolves in priority order (last wins):

1. **Defaults** — hardcoded in the script (client_id, redirect_uri, mcp_endpoint, platform-detected paths)
2. **User config** — `config.json` in the platform config directory
3. **Project config** — `.asana-mcp.json` in the current working directory (repo root)
4. **Environment variables** — `ASANA_CLIENT_ID`, `ASANA_CLIENT_SECRET`, `ASANA_REDIRECT_URI`, `ASANA_MCP_ENDPOINT`, `ASANA_TOKEN_FILE`

### Config Directories by Platform

| Platform | Config directory |
|----------|-----------------|
| Windows  | `%APPDATA%\asana-mcp\` |
| macOS    | `~/Library/Application Support/asana-mcp/` |
| Linux    | `~/.config/asana-mcp/` |

### Project Override

To override settings for a specific repo, create `.asana-mcp.json` at the repo root:

```json
{
  "client_id": "different-app-id",
  "mcp_endpoint": "https://custom-mcp-proxy.example.com/v2/mcp"
}
```

Only keys present in the override file are applied; all others fall through to user config or defaults.

## Token Lifecycle

- Access tokens expire after **1 hour** (3600 seconds)
- The script stores `obtained_at` timestamp alongside the token for validity checks
- A 2-minute safety margin is applied (tokens considered expired at T-120s)
- Refresh tokens survive across sessions and are stored in `token.json`
- Token and config files have restricted permissions (0600) on macOS/Linux

## Troubleshooting

**"This endpoint requires an API app"** — The token is MCP-scoped. Do not use it against `app.asana.com/api/1.0`. Use MCP JSON-RPC calls only.

**Token refresh fails** — The refresh token may have been revoked. Run `auth --force` to re-authorize.

**IDE config not found** — Run `status` to see all detected paths. Use `update-mcp --target <name>` to create a specific one, or `--path` for a custom location.

**SSE vs JSON responses** — The MCP endpoint may respond with either `application/json` or `text/event-stream`. The script handles both transparently.

## Protocol Reference

For detailed MCP JSON-RPC protocol documentation (headers, session lifecycle, request/response formats, available tools), see:

`${CLAUDE_PLUGIN_ROOT}/skills/asana-mcp/references/mcp-protocol.md`
