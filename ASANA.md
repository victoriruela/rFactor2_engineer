# Asana MCP Integration

Asana MCP authentication and configuration is managed by the **`asana-mcp` Claude Code plugin**.

## Install

Unzip the plugin into `~/.claude/asana-mcp/`:

```bash
# macOS / Linux
mkdir -p ~/.claude/asana-mcp && unzip asana-mcp-plugin.zip -d ~/.claude/asana-mcp/

# Windows (PowerShell)
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.claude\asana-mcp"
Expand-Archive -Path asana-mcp-plugin.zip -DestinationPath "$env:USERPROFILE\.claude\asana-mcp"
```

## Quick Reference

```bash
# Check current status (token, config, IDE configs detected)
python ~/.claude/asana-mcp/scripts/asana_mcp.py status

# First-time setup (creates config.json)
python ~/.claude/asana-mcp/scripts/asana_mcp.py setup

# Authenticate (refresh or full OAuth2)
python ~/.claude/asana-mcp/scripts/asana_mcp.py auth

# Write token into all detected IDE configs
python ~/.claude/asana-mcp/scripts/asana_mcp.py update-mcp

# Write to specific IDE(s)
python ~/.claude/asana-mcp/scripts/asana_mcp.py update-mcp --target copilot-vscode claude-desktop

# Write to all IDEs (even if config doesn't exist yet)
python ~/.claude/asana-mcp/scripts/asana_mcp.py update-mcp --all

# Smoke test MCP connection
python ~/.claude/asana-mcp/scripts/asana_mcp.py test
```

## Supported IDEs

| Target              | Format                                             |
|---------------------|----------------------------------------------------|
| `copilot-jetbrains` | `servers.asana-mcp.requestInit.headers`             |
| `copilot-vscode`    | `servers.asana-mcp` with `type`/`url`/`headers`    |
| `claude-desktop`    | `mcpServers.asana-mcp` with `type`/`url`/`headers` |
| `claude-cli`        | `mcpServers.asana-mcp` with `type`/`url`/`headers` |

## Project Override

To override config for this repo, create `.asana-mcp.json` at the repo root with any keys to override (e.g. `client_id`, `mcp_endpoint`).

## Full Documentation

See the plugin's skill and reference files:
- `~/.claude/asana-mcp/skills/asana-mcp/SKILL.md`
- `~/.claude/asana-mcp/skills/asana-mcp/references/mcp-protocol.md`
