"""Automation, script, and scene config editing — Group B.

These use the ``config`` integration's HTTP endpoints (not REST states), reusing
the existing bearer-token HTTPClient. Saving validates and reloads the item, so no
separate reload is needed. Failures are raised (not returned) for consistency with
the WebSocket tools.

The config ``object_id`` is distinct from the entity_id. For an automation it
equals the automation entity's registry ``unique_id`` — resolve it with
``get_entity_registry_entry`` when only the entity_id is known.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ha_mcp.ws_client import HAToolError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from ha_mcp.client import HAClient


_KINDS = ("automation", "script", "scene")


def _raise_on_error(result: Any) -> Any:
    """Raise if HAClient returned its ``{"error": ...}`` failure shape."""
    if isinstance(result, dict) and "error" in result and "detail" in result:
        raise HAToolError(str(result["error"]), str(result.get("detail", "")))
    return result


def register(mcp: FastMCP, ha: HAClient, admin: bool) -> None:
    for kind in _KINDS:
        _register_kind(mcp, ha, kind, admin)


def _register_kind(mcp: FastMCP, ha: HAClient, kind: str, admin: bool) -> None:
    base = f"/api/config/{kind}/config"

    @mcp.tool(name=f"get_{kind}_config")
    async def get_config(object_id: str) -> dict:
        return _raise_on_error(await ha.get(f"{base}/{object_id}"))

    get_config.__doc__ = (
        f"Get the {kind} configuration body.\n\n"
        f"    Args:\n"
        f"        object_id: The {kind} config id (for automations, the entity's unique_id)."
    )

    if not admin:
        return

    @mcp.tool(name=f"set_{kind}_config")
    async def set_config(object_id: str, config: dict) -> dict:
        """Create or update the config, then return the item read back."""
        _raise_on_error(await ha.post(f"{base}/{object_id}", json=config))
        return _raise_on_error(await ha.get(f"{base}/{object_id}"))

    set_config.__doc__ = (
        f"Create or update a {kind}, then return the config read back.\n\n"
        f"    Creates the {kind} when the id does not exist, updates it when it does.\n"
        f"    Writing triggers validation and reload.\n\n"
        f"    Args:\n"
        f"        object_id: The {kind} config id.\n"
        f"        config: The full {kind} configuration body."
    )

    @mcp.tool(name=f"delete_{kind}_config")
    async def delete_config(object_id: str, confirm: bool = False) -> dict:
        if not confirm:
            raise HAToolError(
                "confirmation_required",
                f"set confirm=true to delete {kind} {object_id}",
            )
        return _raise_on_error(await ha.delete(f"{base}/{object_id}"))

    delete_config.__doc__ = (
        f"Delete a {kind} configuration.\n\n"
        f"    Args:\n"
        f"        object_id: The {kind} config id.\n"
        f"        confirm: Must be true to perform this destructive operation."
    )
