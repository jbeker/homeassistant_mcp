# Home Assistant MCP

An MCP server for Home Assistant. It wraps the REST API for states, services,
events, history, templates, and calendars, and adds a WebSocket-backed layer for
the configuration/registry operations the REST API does not expose (entity
renames, automation/script/scene editing, area and device registry edits,
dashboard editing).

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
| `read-only` (default) | REST reads, plus registry/config **reads**: `list_entity_registry`, `get_entity_registry_entry`, `get_*_config`, `list_labels`, `list_categories`, `list_helpers`, `list_config_entries`, `list_backups`, `list_dashboards`, `get_dashboard_config`, `list_dashboard_resources`, and `wait_for_state` |
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
- **Dashboards:** `create_dashboard`/`update_dashboard`/`delete_dashboard`,
  `save_dashboard_config`/`delete_dashboard_config`,
  `set_dashboard_view`/`delete_dashboard_view`,
  `set_dashboard_card`/`delete_dashboard_card`,
  `create_dashboard_resource`/`update_dashboard_resource`/`delete_dashboard_resource`

Destructive operations (`remove_entity_registry_entry`, `delete_area`,
`delete_*_config`, `delete_helper`, `delete_label`, `delete_category`,
`delete_config_entry`, `abort_config_flow`, `abort_options_flow`,
`delete_backup`, `restore_backup`, `delete_dashboard`, `delete_dashboard_config`,
`delete_dashboard_view`, `delete_dashboard_card`, `delete_dashboard_resource`)
require an explicit `confirm: true` argument
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

### Editing dashboards

Dashboards are edited at three levels, all over the WebSocket API:

- **Whole config:** `get_dashboard_config` / `save_dashboard_config` read and
  replace the full `{"views": [...]}` document.
- **One view:** `set_dashboard_view` adds (or, with `view_ref`, replaces) a
  view; `delete_dashboard_view` removes one.
- **One card:** `set_dashboard_card` appends (or, with `card_index`, replaces)
  a card in a view; `delete_dashboard_card` removes one.

Conventions:

- `url_path=None` (the default) addresses the default Overview dashboard. Other
  dashboards use the `url_path` reported by `list_dashboards`, which does not
  list the default one.
- `view_ref` is either an integer index into `views` or the view's `path`.
- Views with `type: "sections"` keep cards inside `sections[i].cards`, so the
  card tools require a `section` index for them and reject it for other views.
- A default dashboard that has never been edited is auto-generated and has no
  stored config; `get_dashboard_config` reports `config_not_found` for it. Take
  control by writing a full config with `save_dashboard_config` first.
- `create_dashboard` makes an empty dashboard; `url_path` must contain a hyphen
  unless `allow_single_word` is set.
- `update_dashboard` and `delete_dashboard` take the dashboard's `id` from
  `list_dashboards`, which is a slug (`garden_view`), not the `url_path`
  (`garden-view`).

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

## License

Copyright (C) 2026 Jeremy Beker

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License as published by the Free
Software Foundation, either version 3 of the License, or (at your option) any
later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along
with this program. If not, see <https://www.gnu.org/licenses/>.
