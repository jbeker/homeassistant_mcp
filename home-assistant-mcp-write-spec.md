# Home Assistant MCP: Implementation Spec for Configuration and Registry Functions

## 1. Purpose and scope

The current MCP wraps the Home Assistant REST API and covers reads, state pushes, event firing, service calls, and template rendering. It does not reach the configuration or registry layer, because the REST API does not expose that layer. This document specifies the functions required to close that gap.

In scope: entity registry, automation, script, and scene configuration, area registry, device registry, helpers, label and category registries, config entries, backups, and a bounded substitute for event subscriptions.

Out of scope: changes to the existing REST-backed tools, and the Supervisor or add-on API, which does not apply to a Home Assistant Container deployment.

Target version for schema verification: 2026.5.0.

## 2. Background

The REST API provides states, services, events, history, logbook, templates, configuration checks, intents, calendars, and camera images. None of the operations below exist in REST. They require one of two transports:

- The WebSocket API at `/api/websocket`, used for all registry commands, helpers, labels, categories, and config entries.
- The HTTP endpoints provided by the `config` integration under `/api/config/...`, used for automation, script, and scene configuration.

A WebSocket client is therefore the central new component.

## 3. Architecture

### 3.1 WebSocket client

Add a persistent WebSocket client with the following responsibilities.

- Connect to `ws(s)://HOST:8123/api/websocket`, derived from the existing base URL. Use `wss` when the base URL is HTTPS.
- Complete the auth handshake: receive `auth_required`, send `{ "type": "auth", "access_token": TOKEN }`, and confirm `auth_ok`. Reuse the long-lived token already configured for REST.
- Correlate requests and responses by an incrementing integer `id`. Each command is `{ "id": N, "type": COMMAND, ... }`. Each reply is `{ "id": N, "type": "result", "success": BOOL, "result": ..., "error": ... }`.
- Maintain a single shared connection with automatic reconnect and a per-command timeout. Serialize `id` allocation. Surface a clear error if the socket drops mid-command.

A single helper, for example `ws_command(type, **fields)`, should send one command, await the matching `id`, and return `result` on success or raise on `success: false`.

### 3.2 Config integration HTTP calls

Automation, script, and scene editing use authenticated HTTP requests with the existing bearer token, against the `config` integration endpoints listed in section 5. No new transport is needed for these beyond the existing HTTP client.

### 3.3 Configuration

No new credentials are required. Add only the derived WebSocket URL and an optional command timeout. Confirm at startup that the `config` and `websocket_api` integrations are loaded by checking `list_components`.

## 4. Cross-cutting requirements

### 4.1 Destructive-operation safeguards

The following operations are destructive or hard to reverse and must require an explicit confirmation argument, for example `confirm: true`, and must refuse to run without it: remove an entity registry entry, delete an automation, script, or scene, delete an area, delete a helper, delete a label or category, disable or delete a config entry, and delete or restore a backup. Renames and attribute updates are reversible and do not require the flag, though they should validate inputs.

### 4.2 Validation

- Validate `new_entity_id` against the pattern `^[a-z0-9_]+\.[a-z0-9_]+$` and confirm the domain is unchanged before calling the registry.
- Reject a rename whose target already exists, and return the existing entry so the caller can decide.
- For automation, script, and scene writes, read the item back after writing and return it, so the caller can verify the result.

### 4.3 Error handling

Map WebSocket `error.code` values, such as `not_found`, `invalid_format`, and `unknown_error`, to structured tool errors that preserve the code and message. Do not swallow failures. For HTTP config endpoints, map non-2xx responses to the same structure.

### 4.4 Schema verification

Several registry commands are stable but not formally documented. Verify exact field names against the running version before release. Two reliable discovery methods: observe the frontend WebSocket traffic in a browser while performing the operation, and read the corresponding data layer in the Home Assistant frontend source. Treat the field lists below as the common, load-bearing subset rather than the complete schema.

### 4.5 Behavioral notes to document for callers

- Renaming an `entity_id` migrates recorder history and long-term statistics automatically, because history is keyed to an internal metadata id. No extra step is required in the MCP.
- Renaming an `entity_id` that is exposed to HomeKit and lacks a `unique_id` causes the HomeKit accessory to be recreated. Entities with a `unique_id` retain their accessory. The MCP should surface the `unique_id` in the entity registry response so callers can anticipate this.
- Saving an automation, script, or scene through the config endpoints validates and reloads it. A separate reload is unnecessary, though `automation.reload` remains available through the existing `call_service` tool.

## 5. Function specifications

Naming follows the existing snake_case convention. Each entry lists the tool, its underlying Home Assistant call, parameters, return value, and notes.

### Group A: Entity registry (priority 1)

**list_entity_registry**
- Underlying: WebSocket `config/entity_registry/list`.
- Parameters: optional `domain` and `area_id` filters applied client side.
- Returns: entries including `entity_id`, `name`, `original_name`, `platform`, `unique_id`, `device_id`, `area_id`, `disabled_by`, `hidden_by`, and `entity_category`. This is richer than the existing `list_entities`, which returns only id, friendly name, and state.

**get_entity_registry_entry**
- Underlying: WebSocket `config/entity_registry/get` with `entity_id`.
- Parameters: `entity_id`.
- Returns: the full registry entry, including `unique_id`.

**update_entity_registry_entry**
- Underlying: WebSocket `config/entity_registry/update`.
- Parameters: `entity_id` (required) and any of `name`, `icon`, `area_id`, `new_entity_id`, `disabled` mapped to `disabled_by`, `hidden` mapped to `hidden_by`, `labels`, and `aliases`.
- Returns: the updated entry.
- Notes: this is the function that performs an `entity_id` rename, through `new_entity_id`.

**rename_entity** (convenience wrapper)
- Underlying: `update_entity_registry_entry` with `new_entity_id`.
- Parameters: `entity_id`, `new_entity_id`.
- Returns: the updated entry.
- Notes: provided because rename is the most common registry operation. Applies the validation in section 4.2.

**remove_entity_registry_entry**
- Underlying: WebSocket `config/entity_registry/remove`.
- Parameters: `entity_id`, `confirm`.
- Returns: success status.
- Notes: only removes entries that the platform allows to be removed.

### Group B: Automation, script, and scene configuration (priority 1)

The numeric or string configuration id is distinct from the entity id. For an automation, the configuration id equals the entity registry `unique_id` of the automation entity. Resolve it through `get_entity_registry_entry` when only the entity id is known.

**get_automation_config**
- Underlying: HTTP GET `/api/config/automation/config/{automation_id}`.
- Parameters: `automation_id`.
- Returns: the automation configuration body.

**set_automation_config**
- Underlying: HTTP POST `/api/config/automation/config/{automation_id}` with the configuration as the JSON body.
- Parameters: `automation_id`, `config`.
- Returns: the configuration read back after the write.
- Notes: creates the automation when the id does not exist, and updates it when it does. Writing triggers validation and reload.

**delete_automation_config**
- Underlying: HTTP DELETE `/api/config/automation/config/{automation_id}`.
- Parameters: `automation_id`, `confirm`.
- Returns: success status.

**patch_automation_config** (convenience)
- Underlying: `get_automation_config`, a structured edit, then `set_automation_config`.
- Parameters: `automation_id`, plus a structured instruction such as adding a condition to a named block.
- Returns: the updated configuration.
- Notes: optional, useful for targeted edits such as inserting a guard condition without resubmitting the whole body. If omitted, callers use get then set.

Provide the same get, set, and delete trio for scripts at `/api/config/script/config/{object_id}` and scenes at `/api/config/scene/config/{scene_id}`. A single generic implementation parameterized by item kind is acceptable, with thin wrappers per kind.

### Group C: Area registry (priority 2)

Relevant to relabeling rooms, including the office and guest room swap.

**list_areas** already exists. Add the following.

**create_area**
- Underlying: WebSocket `config/area_registry/create`.
- Parameters: `name`, optional `icon`, `floor_id`, `aliases`, and `labels`.
- Returns: the created area, including `area_id`.

**update_area**
- Underlying: WebSocket `config/area_registry/update`.
- Parameters: `area_id` (required), and any of `name`, `icon`, `picture`, `floor_id`, `aliases`, and `labels`.
- Returns: the updated area.
- Notes: renaming an area does not affect entity ids or history.

**delete_area**
- Underlying: WebSocket `config/area_registry/delete`.
- Parameters: `area_id`, `confirm`.
- Returns: success status.

### Group D: Device registry (priority 2)

Relevant to correcting a misspelled device name and reassigning a device to an area.

**list_devices** already exists. Add the following.

**update_device**
- Underlying: WebSocket `config/device_registry/update`.
- Parameters: `device_id` (required), and any of `name_by_user`, `area_id`, `disabled` mapped to `disabled_by`, and `labels`.
- Returns: the updated device.
- Notes: `name_by_user` overrides the device name without altering the integration-supplied name. Reassigning a device area moves its entities unless an entity sets its own area override.

### Group E: Helpers (priority 3)

Helpers backed by storage collections expose list, create, update, and delete WebSocket commands under their own domain, for example `input_boolean/create`, `input_boolean/update`, `input_boolean/delete`, and `input_boolean/list`. The same pattern applies to `input_number`, `input_text`, `input_select`, `input_datetime`, `input_button`, `counter`, `timer`, and `schedule`, each with its own fields, such as `min`, `max`, and `step` for `input_number`, and `options` for `input_select`.

**list_helpers**, **create_helper**, **update_helper**, **delete_helper**
- Parameters: `helper_domain` plus the domain-specific fields, and `confirm` for delete.
- Returns: the affected helper.
- Notes: helpers that are config-entry based, such as template, group, threshold, and derivative, are created through the config entry flow in Group G rather than through a collection command. Document this distinction.

### Group F: Label and category registries (priority 3)

**list_labels**, **create_label**, **update_label**, **delete_label**
- Underlying: WebSocket `config/label_registry/list`, `create`, `update`, and `delete`.
- Parameters: `name`, `color`, `icon`, and `description` for create and update, `label_id` for update and delete, and `confirm` for delete.
- Notes: assign labels to entities and devices through `update_entity_registry_entry` and `update_device`.

Provide the equivalent four functions for categories through `config/category_registry/*`, which are scoped, so include a `scope` parameter.

### Group G: Config entries and integrations (priority 4)

**list_config_entries**
- Underlying: WebSocket `config_entries/get`.
- Returns: entries with `entry_id`, `domain`, `title`, `state`, and `disabled_by`.

**reload_config_entry**
- Underlying: HTTP POST `/api/config/config_entries/entry/{entry_id}/reload`.
- Parameters: `entry_id`.

**set_config_entry_disabled**
- Underlying: WebSocket `config_entries/disable` with `disabled_by`.
- Parameters: `entry_id`, `disabled`.

**delete_config_entry**
- Underlying: HTTP DELETE `/api/config/config_entries/entry/{entry_id}`.
- Parameters: `entry_id`, `confirm`.

Setting up a new integration uses the multi-step config flow under `/api/config/config_entries/flow` and is integration specific. Treat it as an advanced, optional addition rather than part of the initial scope.

### Group H: Backups (priority 4)

The simplest path reuses the existing `call_service` tool with the `backup.create` service. For richer control, add functions over the backup WebSocket commands.

**list_backups**, **create_backup**, **delete_backup**
- Underlying: WebSocket `backup/info`, `backup/generate`, and `backup/delete`.
- Parameters: creation options as supported by the version, `backup_id` for delete, and `confirm` for delete.
- Notes: restore is high risk. If included, gate it behind `confirm` and document that it can interrupt the running instance.

### Group I: Event and state subscriptions (architectural note, priority 5)

The WebSocket API offers `subscribe_events`, `subscribe_trigger`, and `subscribe_entities`, which hold an open stream. A request and response MCP tool cannot maintain a subscription, so do not expose these directly. Provide bounded substitutes instead.

**wait_for_state**
- Behavior: open a short-lived `subscribe_trigger` or `subscribe_entities` stream, wait until the target entity reaches a target state or a timeout elapses, then close the stream and return the outcome.
- Parameters: `entity_id`, `target_state`, `timeout_seconds`.
- Returns: whether the target was reached, and the final observed state.

For historical event needs, the existing `get_logbook` and `get_history` tools remain the correct tools.

## 6. Phased implementation plan

1. WebSocket client, auth, request correlation, and error mapping. Group A. This unblocks entity renames.
2. Group B, automation, script, and scene editing over the config HTTP endpoints. This unblocks automation edits.
3. Groups C and D, area and device registries. These support relabeling and device cleanup.
4. Groups E and F, helpers, labels, and categories.
5. Group G, config entries.
6. Group H, backups, and Group I, the bounded wait helper.

## 7. Acceptance criteria

- Renaming an entity through `rename_entity` changes the `entity_id`, preserves history under the new id, and is rejected when the target id already exists or the domain would change.
- Editing an automation through get then set adds a condition and survives a reload, verified by reading the configuration back.
- Creating, renaming, and deleting an area succeeds, and renaming does not alter entity ids.
- Updating a device `name_by_user` and `area_id` succeeds and is reflected in the device registry.
- Every destructive function refuses to run without `confirm: true`.
- WebSocket failures and Home Assistant error codes surface as structured errors rather than silent failures.

## 8. Appendix: WebSocket session example

```
# 1. Connect to ws(s)://HOST:8123/api/websocket
# 2. Server sends:        {"type": "auth_required"}
# 3. Client sends:        {"type": "auth", "access_token": "TOKEN"}
# 4. Server sends:        {"type": "auth_ok"}
# 5. Client sends a command with a unique id:
#    {"id": 1, "type": "config/entity_registry/update",
#     "entity_id": "sensor.gues_room_sensor_humidity",
#     "new_entity_id": "sensor.guest_room_sensor_humidity"}
# 6. Server replies:
#    {"id": 1, "type": "result", "success": true, "result": { ...updated entry... }}
```

The same connection carries every registry, helper, label, category, and config entry command. Automation, script, and scene edits use authenticated HTTP requests with the same token against the `config` integration endpoints.
