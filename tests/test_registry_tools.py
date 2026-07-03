"""Tests for registry/config tool validation and confirm guards.

These exercise the tool callables directly by capturing them from a fake FastMCP
during registration, with a stubbed WebSocket/HTTP client.
"""

from __future__ import annotations

import pytest

from ha_mcp.tools import backups, config_edit, helpers, registry
from ha_mcp.ws_client import HAToolError


class FakeMCP:
    """Captures the functions registered via @mcp.tool() so tests can call them."""

    def __init__(self) -> None:
        self.tools: dict[str, callable] = {}

    def tool(self, name: str | None = None, **kwargs):
        def deco(fn):
            self.tools[name or fn.__name__] = fn
            return fn

        return deco


class FakeWS:
    def __init__(self, *, entries=None, result=None) -> None:
        self.entries = entries or []
        self.result = result if result is not None else {"ok": True}
        self.calls: list[tuple] = []

    async def ws_command(self, type, **fields):
        self.calls.append((type, fields))
        if type == "config/entity_registry/list":
            return self.entries
        return self.result


class FakeHTTP:
    def __init__(self, response=None) -> None:
        self.response = response if response is not None else {"alias": "x"}
        self.calls: list[tuple] = []

    async def get(self, path, **kw):
        self.calls.append(("get", path))
        return self.response

    async def post(self, path, json=None, **kw):
        self.calls.append(("post", path, json))
        return self.response

    async def delete(self, path, **kw):
        self.calls.append(("delete", path))
        return self.response


def _registry_tools(ws, *, admin=True):
    mcp = FakeMCP()
    registry.register(mcp, ha=None, ws=ws, admin=admin)
    return mcp.tools


def _config_tools(ha, *, ws=None, admin=True):
    mcp = FakeMCP()
    config_edit.register(mcp, ha=ha, ws=ws or FakeWS(), admin=admin)
    return mcp.tools


def _helper_tools(ws, *, admin=True):
    mcp = FakeMCP()
    helpers.register(mcp, ws=ws, admin=admin)
    return mcp.tools


def _backup_tools(ws, *, admin=True):
    mcp = FakeMCP()
    backups.register(mcp, ws=ws, admin=admin)
    return mcp.tools


# -- rename_entity validation -------------------------------------------------


async def test_rename_rejects_bad_format():
    tools = _registry_tools(FakeWS())
    with pytest.raises(HAToolError) as exc:
        await tools["rename_entity"]("sensor.a", "Sensor.A")  # uppercase invalid
    assert exc.value.code == "invalid_entity_id"


async def test_rename_rejects_domain_change():
    tools = _registry_tools(FakeWS())
    with pytest.raises(HAToolError) as exc:
        await tools["rename_entity"]("sensor.a", "binary_sensor.a")
    assert exc.value.code == "domain_change_forbidden"


async def test_rename_rejects_existing_target():
    ws = FakeWS(entries=[{"entity_id": "sensor.taken"}])
    tools = _registry_tools(ws)
    with pytest.raises(HAToolError) as exc:
        await tools["rename_entity"]("sensor.a", "sensor.taken")
    assert exc.value.code == "target_exists"


async def test_rename_succeeds():
    ws = FakeWS(entries=[{"entity_id": "sensor.other"}], result={"entity_id": "sensor.b"})
    tools = _registry_tools(ws)
    out = await tools["rename_entity"]("sensor.a", "sensor.b")
    assert out == {"entity_id": "sensor.b"}
    update = next(c for c in ws.calls if c[0] == "config/entity_registry/update")
    assert update[1] == {"entity_id": "sensor.a", "new_entity_id": "sensor.b"}


# -- confirm guards run before any network call -------------------------------


async def test_remove_entity_requires_confirm():
    ws = FakeWS()
    tools = _registry_tools(ws)
    with pytest.raises(HAToolError) as exc:
        await tools["remove_entity_registry_entry"]("sensor.a")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []  # no network call


async def test_delete_area_requires_confirm():
    ws = FakeWS()
    tools = _registry_tools(ws)
    with pytest.raises(HAToolError) as exc:
        await tools["delete_area"]("area_1")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_delete_automation_requires_confirm():
    ha = FakeHTTP()
    tools = _config_tools(ha)
    with pytest.raises(HAToolError) as exc:
        await tools["delete_automation_config"]("123")
    assert exc.value.code == "confirmation_required"
    assert ha.calls == []


# -- update_device maps disabled -> disabled_by -------------------------------


async def test_update_device_maps_disabled():
    ws = FakeWS()
    tools = _registry_tools(ws)
    await tools["update_device"]("dev1", name_by_user="Den", disabled=True)
    call = ws.calls[0]
    assert call[0] == "config/device_registry/update"
    assert call[1]["disabled_by"] == "user"
    assert call[1]["name_by_user"] == "Den"
    assert "area_id" not in call[1]  # None values dropped


# -- admin gating: read tools present, mutations absent without admin ---------


def test_non_admin_omits_mutations():
    tools = _registry_tools(FakeWS(), admin=False)
    assert "list_entity_registry" in tools
    assert "rename_entity" not in tools


# -- _raise_on_error ----------------------------------------------------------


def test_raise_on_error_passthrough():
    assert config_edit._raise_on_error({"alias": "x"}) == {"alias": "x"}


def test_raise_on_error_raises():
    with pytest.raises(HAToolError) as exc:
        config_edit._raise_on_error({"error": "HTTP 404", "detail": "not found"})
    assert exc.value.code == "HTTP 404"


async def test_set_config_reads_back():
    ha = FakeHTTP(response={"alias": "Test", "trigger": []})
    tools = _config_tools(ha)
    out = await tools["set_automation_config"]("abc", {"alias": "Test"})
    assert out == {"alias": "Test", "trigger": []}
    assert [c[0] for c in ha.calls] == ["post", "get"]  # write then read-back


# -- Group E: helpers ---------------------------------------------------------


async def test_create_helper_passes_fields():
    ws = FakeWS(result={"id": "h1", "name": "Vacation"})
    tools = _helper_tools(ws)
    out = await tools["create_helper"]("input_boolean", {"name": "Vacation"})
    assert out == {"id": "h1", "name": "Vacation"}
    assert ws.calls[0] == ("input_boolean/create", {"name": "Vacation"})


async def test_update_helper_uses_domain_id_key():
    ws = FakeWS()
    tools = _helper_tools(ws)
    await tools["update_helper"]("input_number", "abc", {"max": 50})
    assert ws.calls[0] == ("input_number/update", {"input_number_id": "abc", "max": 50})


async def test_delete_helper_requires_confirm():
    ws = FakeWS()
    tools = _helper_tools(ws)
    with pytest.raises(HAToolError) as exc:
        await tools["delete_helper"]("counter", "c1")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_delete_helper_uses_domain_id_key():
    ws = FakeWS()
    tools = _helper_tools(ws)
    await tools["delete_helper"]("schedule", "s1", confirm=True)
    assert ws.calls[0] == ("schedule/delete", {"schedule_id": "s1"})


async def test_helper_rejects_unknown_domain():
    ws = FakeWS()
    tools = _helper_tools(ws)
    with pytest.raises(HAToolError) as exc:
        await tools["list_helpers"]("template")
    assert exc.value.code == "invalid_helper_domain"
    assert ws.calls == []


def test_helpers_non_admin_omits_mutations():
    tools = _helper_tools(FakeWS(), admin=False)
    assert "list_helpers" in tools
    assert "create_helper" not in tools


# -- Group F: labels & categories ---------------------------------------------


async def test_create_label_drops_none():
    ws = FakeWS(result={"label_id": "l1"})
    tools = _registry_tools(ws)
    await tools["create_label"]("Critical", color="red")
    cmd, fields = ws.calls[0]
    assert cmd == "config/label_registry/create"
    assert fields == {"name": "Critical", "color": "red"}  # icon/description dropped


async def test_delete_label_requires_confirm():
    ws = FakeWS()
    tools = _registry_tools(ws)
    with pytest.raises(HAToolError) as exc:
        await tools["delete_label"]("l1")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_category_tools_pass_scope():
    ws = FakeWS(result={"category_id": "c1"})
    tools = _registry_tools(ws)
    await tools["create_category"]("automation", "Lighting")
    assert ws.calls[0] == (
        "config/category_registry/create",
        {"scope": "automation", "name": "Lighting"},
    )
    await tools["delete_category"]("automation", "c1", confirm=True)
    assert ws.calls[1] == (
        "config/category_registry/delete",
        {"scope": "automation", "category_id": "c1"},
    )


async def test_list_categories_passes_scope():
    ws = FakeWS(result=[{"category_id": "c1"}])
    tools = _registry_tools(ws)
    await tools["list_categories"]("script")
    assert ws.calls[0] == ("config/category_registry/list", {"scope": "script"})


# -- Group G: config entries --------------------------------------------------


async def test_list_config_entries_filters_domain():
    ws = FakeWS(result=[{"domain": "hue", "entry_id": "1"}, {"domain": "mqtt", "entry_id": "2"}])
    tools = _config_tools(FakeHTTP(), ws=ws)
    out = await tools["list_config_entries"](domain="hue")
    assert [e["entry_id"] for e in out] == ["1"]


async def test_set_config_entry_disabled_maps_disabled_by():
    ws = FakeWS()
    tools = _config_tools(FakeHTTP(), ws=ws)
    await tools["set_config_entry_disabled"]("e1", True)
    assert ws.calls[0] == ("config_entries/disable", {"entry_id": "e1", "disabled_by": "user"})
    await tools["set_config_entry_disabled"]("e1", False)
    assert ws.calls[1] == ("config_entries/disable", {"entry_id": "e1", "disabled_by": None})


async def test_delete_config_entry_requires_confirm():
    ha = FakeHTTP()
    tools = _config_tools(ha)
    with pytest.raises(HAToolError) as exc:
        await tools["delete_config_entry"]("e1")
    assert exc.value.code == "confirmation_required"
    assert ha.calls == []


def test_config_entries_non_admin_omits_mutations():
    tools = _config_tools(FakeHTTP(), admin=False)
    assert "list_config_entries" in tools
    assert "delete_config_entry" not in tools
    assert "reload_config_entry" not in tools


# -- Config flows (entry creation) --------------------------------------------


async def test_start_config_flow_posts_handler():
    ha = FakeHTTP(response={"type": "form", "flow_id": "f1", "data_schema": []})
    tools = _config_tools(ha)
    out = await tools["start_config_flow"]("dew_point")
    assert out["flow_id"] == "f1"
    assert ha.calls[0] == (
        "post",
        "/api/config/config_entries/flow",
        {"handler": "dew_point", "show_advanced_options": False},
    )


async def test_submit_config_flow_step_posts_user_input():
    ha = FakeHTTP(response={"type": "create_entry"})
    tools = _config_tools(ha)
    user_input = {"name": "Guest Bedroom", "temperature_sensor": "sensor.x"}
    out = await tools["submit_config_flow_step"]("f1", user_input)
    assert out == {"type": "create_entry"}
    assert ha.calls[0] == ("post", "/api/config/config_entries/flow/f1", user_input)


async def test_get_config_flow():
    ha = FakeHTTP(response={"type": "form", "step_id": "user"})
    tools = _config_tools(ha)
    await tools["get_config_flow"]("f1")
    assert ha.calls[0] == ("get", "/api/config/config_entries/flow/f1")


async def test_abort_config_flow_requires_confirm():
    ha = FakeHTTP()
    tools = _config_tools(ha)
    with pytest.raises(HAToolError) as exc:
        await tools["abort_config_flow"]("f1")
    assert exc.value.code == "confirmation_required"
    assert ha.calls == []


async def test_abort_config_flow_with_confirm():
    ha = FakeHTTP(response={"ok": True})
    tools = _config_tools(ha)
    await tools["abort_config_flow"]("f1", confirm=True)
    assert ha.calls[0] == ("delete", "/api/config/config_entries/flow/f1")


def test_config_flow_tools_are_admin_only():
    tools = _config_tools(FakeHTTP(), admin=False)
    assert "start_config_flow" not in tools
    assert "submit_config_flow_step" not in tools


# -- Options flows ------------------------------------------------------------


async def test_start_options_flow_posts_entry_id_as_handler():
    ha = FakeHTTP(response={"type": "form", "flow_id": "of1"})
    tools = _config_tools(ha)
    out = await tools["start_options_flow"]("entry123")
    assert out["flow_id"] == "of1"
    assert ha.calls[0] == (
        "post",
        "/api/config/config_entries/options/flow",
        {"handler": "entry123", "show_advanced_options": False},
    )


async def test_submit_options_flow_step():
    ha = FakeHTTP(response={"type": "create_entry"})
    tools = _config_tools(ha)
    await tools["submit_options_flow_step"]("of1", {"scan_interval": 30})
    assert ha.calls[0] == (
        "post",
        "/api/config/config_entries/options/flow/of1",
        {"scan_interval": 30},
    )


async def test_abort_options_flow_requires_confirm():
    ha = FakeHTTP()
    tools = _config_tools(ha)
    with pytest.raises(HAToolError) as exc:
        await tools["abort_options_flow"]("of1")
    assert exc.value.code == "confirmation_required"
    assert ha.calls == []


# -- Group H: backups ---------------------------------------------------------


async def test_list_backups():
    ws = FakeWS(result={"backups": [{"backup_id": "b1"}]})
    tools = _backup_tools(ws)
    out = await tools["list_backups"]()
    assert out == {"backups": [{"backup_id": "b1"}]}
    assert ws.calls[0] == ("backup/info", {})


async def test_create_backup_passes_options():
    ws = FakeWS(result={"backup_job_id": "j1"})
    tools = _backup_tools(ws)
    await tools["create_backup"]({"name": "Pre-update", "agent_ids": ["backup.local"]})
    assert ws.calls[0] == (
        "backup/generate",
        {"name": "Pre-update", "agent_ids": ["backup.local"]},
    )


async def test_create_backup_defaults_to_empty():
    ws = FakeWS()
    tools = _backup_tools(ws)
    await tools["create_backup"]()
    assert ws.calls[0] == ("backup/generate", {})


async def test_delete_backup_requires_confirm():
    ws = FakeWS()
    tools = _backup_tools(ws)
    with pytest.raises(HAToolError) as exc:
        await tools["delete_backup"]("b1")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_delete_backup_with_confirm():
    ws = FakeWS()
    tools = _backup_tools(ws)
    await tools["delete_backup"]("b1", confirm=True)
    assert ws.calls[0] == ("backup/delete", {"backup_id": "b1"})


async def test_restore_backup_requires_confirm():
    ws = FakeWS()
    tools = _backup_tools(ws)
    with pytest.raises(HAToolError) as exc:
        await tools["restore_backup"]("b1")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_restore_backup_with_confirm_and_options():
    ws = FakeWS()
    tools = _backup_tools(ws)
    await tools["restore_backup"]("b1", confirm=True, options={"agent_id": "backup.local"})
    assert ws.calls[0] == (
        "backup/restore",
        {"backup_id": "b1", "agent_id": "backup.local"},
    )


def test_backups_non_admin_omits_mutations():
    tools = _backup_tools(FakeWS(), admin=False)
    assert "list_backups" in tools
    assert "create_backup" not in tools
    assert "restore_backup" not in tools
