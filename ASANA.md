# Asana MCP Integration

## Overview

This repo contains tooling to authenticate with Asana via OAuth2 and interact with the **Asana MCP endpoint** (`https://mcp.asana.com/v2/mcp`).

**Important:** The OAuth2 app (CLIENT_ID `1213839429134637`) is registered as an **MCP-scoped app**. The tokens it issues have `"aud": "mcp-service"` and **only** work against the MCP endpoint — they do **not** work against the standard Asana REST API (`app.asana.com/api/1.0`). Attempting REST API calls with this token returns `"This endpoint requires an API app"`.

---

## Working script

**`app/asana_oauth2_test.py`** — the canonical, tested script for OAuth2 + MCP access.

### What it does

1. **Token lifecycle management** — loads `asana_token.json`, auto-refreshes if expired, falls back to full browser-based OAuth2 if refresh fails.
2. **MCP JSON-RPC handshake** — sends `initialize` → `notifications/initialized` → `tools/list` → `tools/call`.
3. **Smoke test** — calls `get_me` to verify authenticated access.

### Usage

```bash
# Normal run (reuses/refreshes existing token)
python app/asana_oauth2_test.py

# Force full re-authorization (opens browser)
python app/asana_oauth2_test.py --reauth

# Also write the token into Copilot's mcp.json (Windows machine only)
python app/asana_oauth2_test.py --update-mcp

# Combine flags as needed
python app/asana_oauth2_test.py --reauth --update-mcp
```

### Expected output (verified 2026-03-28)

```
1. initialize    → ✓ Server: Asana OAuth Proxy v1.0.0, Protocol: 2024-11-05
2. initialized   → HTTP 202
3. tools/list    → ✓ 22 tools available
4. tools/call    → ✓ get_me returns user info (name, email, workspaces)
```

---

## OAuth2 flow details

| Parameter       | Value                                          |
|-----------------|------------------------------------------------|
| Authorize URL   | `https://app.asana.com/-/oauth_authorize`      |
| Token URL       | `https://app.asana.com/-/oauth_token`          |
| Redirect URI    | `https://localhost/`                            |
| Grant type      | `authorization_code` (initial), `refresh_token` (renewal) |
| Token lifetime  | 3600s (1 hour)                                 |
| Token audience  | `mcp-service`                                  |
| Scopes          | `default identity`                             |

### Token flow

```
Browser consent → redirect to https://localhost/?code=XXX
        ↓
POST /oauth_token  (grant_type=authorization_code, code=XXX)
        ↓
{access_token, refresh_token, expires_in: 3600}  → saved to asana_token.json
        ↓
On expiry: POST /oauth_token  (grant_type=refresh_token)
        ↓
New {access_token, refresh_token}  → saved to asana_token.json
```

---

## MCP protocol details

The MCP endpoint uses **JSON-RPC 2.0 over HTTP** with optional SSE streaming.

### Endpoint

```
POST https://mcp.asana.com/v2/mcp
```

### Required headers

| Header            | Value                                    |
|-------------------|------------------------------------------|
| `Authorization`   | `Bearer <access_token>`                  |
| `Content-Type`    | `application/json`                       |
| `Accept`          | `application/json, text/event-stream`    |
| `Mcp-Session-Id`  | Returned by server on `initialize` — must be sent on all subsequent requests |

### Session lifecycle

```
1. POST  initialize              → server returns Mcp-Session-Id in response header
2. POST  notifications/initialized  (notification, no "id" field, no response expected)
3. POST  tools/list              → returns available tools
4. POST  tools/call              → invoke a specific tool
```

### JSON-RPC request format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2024-11-05",
    "capabilities": {},
    "clientInfo": {"name": "my-client", "version": "1.0.0"}
  }
}
```

### Response formats

The server may respond with either:
- `Content-Type: application/json` — standard JSON-RPC response body
- `Content-Type: text/event-stream` — SSE stream where JSON-RPC messages appear in `data:` lines

Both must be handled. The script's `parse_mcp_response()` handles this.

### Available tools (22 as of 2026-03-28)

| Tool                          | Description                                     |
|-------------------------------|-------------------------------------------------|
| `get_me`                      | Current authenticated user info                 |
| `get_tasks`                   | List tasks (by workspace/project/tag/section)   |
| `get_task`                    | Full task details by ID                         |
| `create_tasks`                | Create one or more tasks                        |
| `update_tasks`                | Update one or more tasks                        |
| `delete_task`                 | Delete a task                                   |
| `search_tasks`                | Full-text search (premium only)                 |
| `get_projects`                | List projects in workspace                      |
| `get_project`                 | Project details by ID                           |
| `create_project`              | Create project with sections/tasks              |
| `create_project_status_update`| Post status update to project/portfolio         |
| `get_status_overview`         | Status overview for initiatives                 |
| `get_portfolios`              | List portfolios in workspace                    |
| `get_portfolio`               | Portfolio details by ID                         |
| `get_items_for_portfolio`     | Items within a portfolio                        |
| `get_attachments`             | Attachments for project/task                    |
| `add_comment`                 | Add comment to a task                           |
| `get_users`                   | List users in workspace                         |
| `get_user`                    | User details by ID                              |
| `get_teams`                   | List teams in workspace                         |
| `search_objects`              | General object search                           |
| `get_my_tasks`                | Current user's assigned tasks                   |

---

## Files in this repo

| File                              | Status    | Purpose                                        |
|-----------------------------------|-----------|-------------------------------------------------|
| `app/asana_oauth2_test.py`        | **current** | OAuth2 + MCP test script (use this one)       |
| `asana_token.json`                | generated | Persisted OAuth2 tokens (auto-managed)          |
| `app/asana_mcp_oauth2.py`         | legacy    | Original OAuth2 flow — updates mcp.json only    |
| `app/asana_token_manager.py`      | legacy    | Token manager — updates mcp.json only           |
| `app/test_mcp_*.py`               | legacy    | Various MCP session experiments (before we understood the protocol) |
| `app/decode_mcp_token.py`         | legacy    | JWT decoder for debugging                       |
| `app/debug_mcp_bytes.py`          | legacy    | mcp.json encoding diagnostic                    |

---

## For the Windows machine (mcp.json integration)

Once the OAuth2 flow and MCP access are confirmed working (which they are), the next step is to configure the MCP proxy on the target Windows machine at:

```
%USERPROFILE%\AppData\Local\github-copilot\intellij\mcp.json
```

The mcp.json needs:

```json
{
  "servers": {
    "asana-mcp": {
      "url": "https://mcp.asana.com/v2/mcp",
      "requestInit": {
        "headers": {
          "Authorization": "Bearer <access_token>",
          "Accept": "application/json, text/event-stream"
        }
      }
    }
  }
}
```

**Note:** Do **not** hardcode `Mcp-Session-Id` in mcp.json — it must be generated per connection by the MCP client at runtime. The legacy scripts (`asana_token_manager.py`) incorrectly persisted a static UUID there.

**Token refresh:** The access token expires every hour. On the Windows machine, run:

```bash
python app/asana_oauth2_test.py --update-mcp
```

This refreshes the token (if needed) and writes it into mcp.json. Can be scheduled as a recurring task.
