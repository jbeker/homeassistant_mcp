# SPDX-FileCopyrightText: 2026 Jeremy Beker <gothmog@confusticate.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for dashboard (Lovelace) tools: read-modify-write, validation, guards."""

from __future__ import annotations

import copy

import pytest

from ha_mcp.tools import dashboards
from ha_mcp.ws_client import HAToolError
from tests.test_registry_tools import FakeMCP


def _config():
    return {
        "title": "Home",
        "views": [
            {"title": "Main", "path": "main", "cards": [{"type": "markdown", "content": "a"}]},
            {
                "title": "Grid",
                "path": "grid",
                "type": "sections",
                "sections": [{"type": "grid", "cards": [{"type": "button"}]}],
            },
        ],
    }


class FakeDashboardWS:
    """Records calls; serves a stored config and applies saves to it."""

    def __init__(self, config=None, result=None) -> None:
        self.config = copy.deepcopy(config) if config is not None else _config()
        self.result = result if result is not None else {"ok": True}
        self.calls: list[tuple] = []

    async def ws_command(self, type, **fields):
        self.calls.append((type, fields))
        if type == "lovelace/config":
            return copy.deepcopy(self.config)
        if type == "lovelace/config/save":
            self.config = copy.deepcopy(fields["config"])
            return None
        return self.result


def _tools(ws=None, *, admin=True):
    mcp = FakeMCP()
    dashboards.register(mcp, ws=ws or FakeDashboardWS(), admin=admin)
    return mcp.tools


# -- reads --------------------------------------------------------------------


async def test_list_dashboards():
    ws = FakeDashboardWS(result=[{"id": "garden", "url_path": "garden"}])
    out = await _tools(ws)["list_dashboards"]()
    assert out == [{"id": "garden", "url_path": "garden"}]
    assert ws.calls == [("lovelace/dashboards/list", {})]


async def test_get_dashboard_config_default_and_named():
    ws = FakeDashboardWS()
    tools = _tools(ws)
    await tools["get_dashboard_config"]()
    await tools["get_dashboard_config"]("garden", force=True)
    assert ws.calls == [
        ("lovelace/config", {"url_path": None, "force": False}),
        ("lovelace/config", {"url_path": "garden", "force": True}),
    ]


async def test_list_dashboard_resources():
    ws = FakeDashboardWS(result=[{"id": "r1"}])
    await _tools(ws)["list_dashboard_resources"]()
    assert ws.calls == [("lovelace/resources", {})]


def test_non_admin_exposes_only_reads():
    tools = _tools(admin=False)
    assert set(tools) == {
        "list_dashboards", "get_dashboard_config", "list_dashboard_resources"
    }


# -- dashboards ---------------------------------------------------------------


async def test_create_dashboard_defaults():
    ws = FakeDashboardWS(result={"id": "garden-view"})
    await _tools(ws)["create_dashboard"]("garden-view", "Garden")
    assert ws.calls[0] == (
        "lovelace/dashboards/create",
        {
            "url_path": "garden-view",
            "title": "Garden",
            "require_admin": False,
            "show_in_sidebar": True,
        },
    )


async def test_create_dashboard_single_word_and_icon():
    ws = FakeDashboardWS()
    await _tools(ws)["create_dashboard"](
        "garden", "Garden", icon="mdi:flower", allow_single_word=True
    )
    fields = ws.calls[0][1]
    assert fields["icon"] == "mdi:flower"
    assert fields["allow_single_word"] is True


async def test_update_dashboard_drops_none():
    ws = FakeDashboardWS()
    await _tools(ws)["update_dashboard"]("garden", title="Yard", show_in_sidebar=False)
    assert ws.calls[0] == (
        "lovelace/dashboards/update",
        {"dashboard_id": "garden", "title": "Yard", "show_in_sidebar": False},
    )


async def test_delete_dashboard_requires_confirm():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["delete_dashboard"]("garden")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_delete_dashboard_with_confirm():
    ws = FakeDashboardWS(result=None)
    out = await _tools(ws)["delete_dashboard"]("garden", confirm=True)
    assert out == {"deleted": True, "dashboard_id": "garden"}
    assert ws.calls == [("lovelace/dashboards/delete", {"dashboard_id": "garden"})]


# -- whole config -------------------------------------------------------------


async def test_save_dashboard_config_reads_back():
    ws = FakeDashboardWS()
    new = {"views": [{"title": "Only"}]}
    out = await _tools(ws)["save_dashboard_config"](new, url_path="garden")
    assert out == new
    assert [c[0] for c in ws.calls] == ["lovelace/config/save", "lovelace/config"]
    assert ws.calls[0][1] == {"url_path": "garden", "config": new}
    assert ws.calls[1][1] == {"url_path": "garden", "force": True}


async def test_save_dashboard_config_rejects_missing_views():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["save_dashboard_config"]({"title": "x"})
    assert exc.value.code == "invalid_config"
    assert ws.calls == []


async def test_delete_dashboard_config_requires_confirm():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["delete_dashboard_config"]("garden")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_delete_dashboard_config_with_confirm():
    ws = FakeDashboardWS()
    out = await _tools(ws)["delete_dashboard_config"](confirm=True)
    assert out == {"deleted": True, "url_path": None}
    assert ws.calls == [("lovelace/config/delete", {"url_path": None})]


# -- views --------------------------------------------------------------------


async def test_set_view_appends():
    ws = FakeDashboardWS()
    out = await _tools(ws)["set_dashboard_view"]({"title": "New", "path": "new"})
    assert out == {"index": 2, "view": {"title": "New", "path": "new"}}
    assert [v["path"] for v in ws.config["views"]] == ["main", "grid", "new"]
    assert [c[0] for c in ws.calls] == [
        "lovelace/config", "lovelace/config/save", "lovelace/config"
    ]


async def test_set_view_inserts_at_position():
    ws = FakeDashboardWS()
    out = await _tools(ws)["set_dashboard_view"]({"path": "first"}, position=0)
    assert out["index"] == 0
    assert [v["path"] for v in ws.config["views"]] == ["first", "main", "grid"]


async def test_set_view_rejects_bad_position():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["set_dashboard_view"]({"path": "x"}, position=5)
    assert exc.value.code == "position_out_of_range"
    assert len(ws.calls) == 1  # only the load, no save


async def test_set_view_replaces_by_index_and_path():
    ws = FakeDashboardWS()
    tools = _tools(ws)
    await tools["set_dashboard_view"]({"path": "main", "title": "Main2"}, view_ref=0)
    assert ws.config["views"][0] == {"path": "main", "title": "Main2"}
    out = await tools["set_dashboard_view"]({"path": "grid", "title": "G2"}, view_ref="grid")
    assert out["index"] == 1
    assert ws.config["views"][1] == {"path": "grid", "title": "G2"}


async def test_set_view_unknown_path():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["set_dashboard_view"]({}, view_ref="nope")
    assert exc.value.code == "view_not_found"
    assert "main" in exc.value.message


async def test_delete_view_requires_confirm():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["delete_dashboard_view"]("main")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_delete_view_by_path():
    ws = FakeDashboardWS()
    out = await _tools(ws)["delete_dashboard_view"]("main", confirm=True)
    assert out == [{"index": 0, "title": "Grid", "path": "grid"}]
    assert [v["path"] for v in ws.config["views"]] == ["grid"]


# -- cards --------------------------------------------------------------------


async def test_set_card_appends_in_masonry_view():
    ws = FakeDashboardWS()
    card = {"type": "markdown", "content": "b"}
    out = await _tools(ws)["set_dashboard_card"](card, "main")
    assert out == {"view": 0, "section": None, "index": 1, "card": card}
    assert ws.config["views"][0]["cards"][1] == card


async def test_set_card_replaces_by_index():
    ws = FakeDashboardWS()
    card = {"type": "markdown", "content": "replaced"}
    out = await _tools(ws)["set_dashboard_card"](card, 0, card_index=0)
    assert out["index"] == 0
    assert ws.config["views"][0]["cards"] == [card]


async def test_set_card_in_sections_view():
    ws = FakeDashboardWS()
    card = {"type": "tile", "entity": "light.x"}
    out = await _tools(ws)["set_dashboard_card"](card, "grid", section=0)
    assert out == {"view": 1, "section": 0, "index": 1, "card": card}
    assert ws.config["views"][1]["sections"][0]["cards"][1] == card


async def test_set_card_section_required():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["set_dashboard_card"]({}, "grid")
    assert exc.value.code == "section_required"


async def test_set_card_section_not_applicable():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["set_dashboard_card"]({}, "main", section=0)
    assert exc.value.code == "section_not_applicable"


async def test_set_card_section_not_found():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["set_dashboard_card"]({}, "grid", section=3)
    assert exc.value.code == "section_not_found"


async def test_set_card_index_not_found():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["set_dashboard_card"]({}, "main", card_index=7)
    assert exc.value.code == "card_not_found"
    assert len(ws.calls) == 1  # no save


async def test_set_card_creates_cards_list_when_absent():
    ws = FakeDashboardWS(config={"views": [{"title": "Empty"}]})
    out = await _tools(ws)["set_dashboard_card"]({"type": "button"}, 0)
    assert out["index"] == 0
    assert ws.config["views"][0]["cards"] == [{"type": "button"}]


async def test_delete_card_requires_confirm():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["delete_dashboard_card"]("main", 0)
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_delete_card_in_sections_view():
    ws = FakeDashboardWS()
    out = await _tools(ws)["delete_dashboard_card"]("grid", 0, section=0, confirm=True)
    assert out == {"view": 1, "section": 0, "remaining_cards": 0}
    assert ws.config["views"][1]["sections"][0]["cards"] == []


# -- resources ----------------------------------------------------------------


async def test_create_resource():
    ws = FakeDashboardWS(result={"id": "r1"})
    await _tools(ws)["create_dashboard_resource"]("module", "/local/card.js")
    assert ws.calls == [
        ("lovelace/resources/create", {"res_type": "module", "url": "/local/card.js"})
    ]


async def test_create_resource_rejects_bad_type():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["create_dashboard_resource"]("wasm", "/local/x")
    assert exc.value.code == "invalid_resource_type"
    assert ws.calls == []


async def test_update_resource_drops_none():
    ws = FakeDashboardWS()
    await _tools(ws)["update_dashboard_resource"]("r1", url="/local/new.js")
    assert ws.calls == [
        ("lovelace/resources/update", {"resource_id": "r1", "url": "/local/new.js"})
    ]


async def test_delete_resource_requires_confirm():
    ws = FakeDashboardWS()
    with pytest.raises(HAToolError) as exc:
        await _tools(ws)["delete_dashboard_resource"]("r1")
    assert exc.value.code == "confirmation_required"
    assert ws.calls == []


async def test_delete_resource_with_confirm():
    ws = FakeDashboardWS()
    out = await _tools(ws)["delete_dashboard_resource"]("r1", confirm=True)
    assert out == {"deleted": True, "resource_id": "r1"}
    assert ws.calls == [("lovelace/resources/delete", {"resource_id": "r1"})]
