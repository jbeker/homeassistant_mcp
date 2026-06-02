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
| `read-only` (default) | REST reads, plus registry/config **reads**: `list_entity_registry`, `get_entity_registry_entry`, `get_*_config`, `list_labels`, `list_categories`, `list_helpers`, `list_config_entries`, `list_backups`, and `wait_for_state` |
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
- **Config flows (create a new integration entry):** `start_config_flow`, `submit_config_flow_step`, `get_config_flow`, `abort_config_flow`
- **Options flows (edit an existing entry):** `start_options_flow`, `submit_options_flow_step`, `get_options_flow`, `abort_options_flow`
- **Backups:** `create_backup`, `delete_backup`, `restore_backup`

Destructive operations (`remove_entity_registry_entry`, `delete_area`,
`delete_*_config`, `delete_helper`, `delete_label`, `delete_category`,
`delete_config_entry`, `abort_config_flow`, `abort_options_flow`,
`delete_backup`, `restore_backup`) require an explicit `confirm: true` argument
and refuse to run without it. `restore_backup` is especially high risk — it can
interrupt the running instance. Renaming an entity migrates its recorder history
automatically.

Config-entry-based helpers (template, group, threshold, derivative) are not
storage collections and cannot be created via `create_helper`; they use the
integration config-flow instead.

### Creating an integration (config flow)

New UI-managed integrations are created through a multi-step flow rather than a
writable config object:

1. `start_config_flow(handler="<domain>")` — returns a `flow_id` and, for a
   `form`, a `data_schema` listing the exact field keys.
2. `submit_config_flow_step(flow_id, user_input)` — submit the step's fields;
   repeat for each `form` until the result is `create_entry` (done) or `abort`.
   A `form` with a populated `errors` field means the input was rejected.
3. After `create_entry`, assign the new entities/device to an area with
   `update_entity_registry_entry` or `update_device` (area is not part of the flow).

### Waiting for a state

`wait_for_state(entity_id, target_state, timeout_seconds=30)` blocks until the
entity reaches `target_state` (or returns immediately if it is already there),
falling back to the last observed state on timeout. It opens a short-lived
WebSocket subscription internally — useful after issuing a command that takes
time to settle (e.g. waiting for `cover.garage` to reach `open`). For historical
data use `get_history` / `get_logbook` instead.

## Development

```sh
uv run pytest
```

Tests run against a fake in-process WebSocket server, so no live Home Assistant
is needed.
