# Home Assistant MCP

An MCP server for Home Assistant. It wraps the REST API for states, services,
events, history, templates, and calendars, and adds a WebSocket-backed layer for
the configuration/registry operations the REST API does not expose (entity
renames, automation/script/scene editing, area and device registry edits).

## Configuration

Set these in a `.env` file (see `.env.example`) or your shell:

- `HA_URL` — e.g. `http://homeassistant.local:8123`
- `HA_TOKEN` — a long-lived access token (Profile → Long-Lived Access Tokens)

The WebSocket URL is derived automatically (`http`→`ws`, `https`→`wss`).
Registry, automation, and device-config commands require a token belonging to an
**admin** user; non-admin tokens get `unauthorized` errors.

## Running

```sh
uv run ha-mcp --mode <mode>
```

### Access modes

| Mode | Tools exposed |
| --- | --- |
| `read-only` (default) | REST reads, plus registry/config **reads** (`list_entity_registry`, `get_entity_registry_entry`, `get_automation_config`, …) |
| `control-only` | read-only + `call_service` |
| `read-write` | control-only + REST state/event writes |
| `admin` | read-write + registry/config **mutations**: `rename_entity`, `update_entity_registry_entry`, `remove_entity_registry_entry`, `create_area`/`update_area`/`delete_area`, `update_device`, and `set_*_config`/`delete_*_config` for automations, scripts, and scenes |

Destructive operations (`remove_entity_registry_entry`, `delete_area`,
`delete_*_config`) require an explicit `confirm: true` argument and refuse to run
without it. Renaming an entity migrates its recorder history automatically.

## Development

```sh
uv run pytest
```

Tests run against a fake in-process WebSocket server, so no live Home Assistant
is needed.
