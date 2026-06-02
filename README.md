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
| `read-only` (default) | REST reads, plus registry/config **reads**: `list_entity_registry`, `get_entity_registry_entry`, `get_*_config`, `list_labels`, `list_categories`, `list_helpers`, `list_config_entries` |
| `control-only` | read-only + `call_service` |
| `read-write` | control-only + REST state/event writes |
| `admin` | read-write + registry/config **mutations** (below) |

### Admin mutation tools

- **Entity registry:** `rename_entity`, `update_entity_registry_entry`, `remove_entity_registry_entry`
- **Areas / devices:** `create_area`/`update_area`/`delete_area`, `update_device`
- **Automations / scripts / scenes:** `set_*_config`/`delete_*_config`
- **Helpers** (`input_boolean`, `input_number`, `input_text`, `input_select`, `input_datetime`, `input_button`, `counter`, `timer`, `schedule`): `create_helper`/`update_helper`/`delete_helper`
- **Labels / categories:** `create_label`/`update_label`/`delete_label`, `create_category`/`update_category`/`delete_category`
- **Config entries (integrations):** `reload_config_entry`, `set_config_entry_disabled`, `delete_config_entry`

Destructive operations (`remove_entity_registry_entry`, `delete_area`,
`delete_*_config`, `delete_helper`, `delete_label`, `delete_category`,
`delete_config_entry`) require an explicit `confirm: true` argument and refuse to
run without it. Renaming an entity migrates its recorder history automatically.

Config-entry-based helpers (template, group, threshold, derivative) are not
storage collections and cannot be created via `create_helper`; they use the
integration config-flow instead.

## Development

```sh
uv run pytest
```

Tests run against a fake in-process WebSocket server, so no live Home Assistant
is needed.
