"""Tests for registry/config tool validation and confirm guards.

These exercise the tool callables directly by capturing them from a fake FastMCP
during registration, with a stubbed WebSocket/HTTP client.
"""

from __future__ import annotations

import pytest

from ha_mcp.tools import config_edit, registry
from ha_mcp.ws_client import HAToolError


class FakeMCP:
    """Captures the functions registered via @mcp.tool() so tests can call them."""

    def __init__(self) -> None:
        self.tools: dict[str, callable] = {}

    def tool(self, name: str | None = None):
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


def _config_tools(ha, *, admin=True):
    mcp = FakeMCP()
    config_edit.register(mcp, ha=ha, admin=admin)
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
