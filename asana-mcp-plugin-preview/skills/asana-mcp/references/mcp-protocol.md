# Asana MCP Protocol Reference

## Endpoint

```
POST https://mcp.asana.com/v2/mcp
```

All communication uses **JSON-RPC 2.0 over HTTP**.

## Required Headers

| Header            | Value                                    |
|-------------------|------------------------------------------|
| `Authorization`   | `Bearer <access_token>`                  |
| `Content-Type`    | `application/json`                       |
| `Accept`          | `application/json, text/event-stream`    |
| `Mcp-Session-Id`  | Returned by server on `initialize` — required on all subsequent requests |

## Session Lifecycle

```
1. POST  initialize                → server returns Mcp-Session-Id in response header
2. POST  notifications/initialized → notification (no "id" field), expect HTTP 202
3. POST  tools/list                → returns available tools
4. POST  tools/call                → invoke a specific tool
```

## Request Format

Standard JSON-RPC 2.0 with method and optional params:

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

Notifications (like `notifications/initialized`) omit the `"id"` field and expect no response body.

## Response Formats

The server may respond with either content-type:

### application/json
Standard JSON-RPC response body.

### text/event-stream (SSE)
Server-Sent Events stream where JSON-RPC messages appear in `data:` lines:
```
data: {"jsonrpc":"2.0","id":1,"result":{...}}
```

Both formats must be handled by the client.

## Initialize Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "protocolVersion": "2024-11-05",
    "serverInfo": {
      "name": "Asana OAuth Proxy",
      "version": "1.0.0"
    },
    "capabilities": {}
  }
}
```

The `Mcp-Session-Id` is returned as an HTTP response header (not in the JSON body).

## tools/call Request

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "method": "tools/call",
  "params": {
    "name": "get_me",
    "arguments": {}
  }
}
```

Response content is an array of typed items:
```json
{
  "result": {
    "content": [
      {"type": "text", "text": "{\"gid\":\"123\",\"name\":\"User\",\"email\":\"user@example.com\"}"}
    ]
  }
}
```

## Available Tools (22 as of 2026-03-28)

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

## OAuth2 Parameters

| Parameter       | Value                                          |
|-----------------|------------------------------------------------|
| Authorize URL   | `https://app.asana.com/-/oauth_authorize`      |
| Token URL       | `https://app.asana.com/-/oauth_token`          |
| Redirect URI    | `https://localhost/` (registered in Asana app)  |
| Grant types     | `authorization_code`, `refresh_token`          |
| Token lifetime  | 3600s (1 hour)                                 |
| Token audience  | `mcp-service`                                  |
| Scopes          | `default identity`                             |
