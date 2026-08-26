# SPDX-FileCopyrightText: 2026 Jeremy Beker <gothmog@confusticate.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Helper (input_*) tools over the WebSocket API — Group E.

Helpers backed by storage collections expose list/create/update/delete WebSocket
commands under their own domain (e.g. ``input_boolean/create``). The update and
delete commands identify the item by a ``<domain>_id`` field.

Config-entry-based helpers (template, group, threshold, derivative) are *not*
storage collections — they are created through the config entry flow, not these
commands.

Read tools register in every mode; mutations register only when ``admin`` is true.
Deletes require ``confirm=True``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ha_mcp.tools._annotations import mutation, read_only
from ha_mcp.ws_client import HAToolError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from ha_mcp.ws_client import HAWebSocketClient


# Storage-collection helper domains and their per-item field, for documentation.
HELPER_DOMAINS = (
    "input_boolean",
    "input_number",
    "input_text",
    "input_select",
    "input_datetime",
    "input_button",
    "counter",
    "timer",
    "schedule",
)


def _check_domain(helper_domain: str) -> None:
    if helper_domain not in HELPER_DOMAINS:
        raise HAToolError(
            "invalid_helper_domain",
            f"{helper_domain!r} is not a storage-collection helper; "
            f"expected one of {', '.join(HELPER_DOMAINS)}",
        )


def register(mcp: FastMCP, ws: HAWebSocketClient, admin: bool) -> None:
    @mcp.tool(annotations=read_only("List Helpers"))
    async def list_helpers(helper_domain: str) -> list[dict]:
        """List storage-collection helpers of a given domain.

        Args:
            helper_domain: One of input_boolean, input_number, input_text,
                input_select, input_datetime, input_button, counter, timer, schedule.
        """
        _check_domain(helper_domain)
        return await ws.ws_command(f"{helper_domain}/list")

    if not admin:
        return

    @mcp.tool(annotations=mutation("Create Helper"))
    async def create_helper(helper_domain: str, fields: dict) -> dict:
        """Create a helper. Returns the created helper.

        Args:
            helper_domain: The helper domain (see list_helpers).
            fields: Domain-specific fields, e.g. {"name": "Vacation"} for
                input_boolean, {"name": "Brightness", "min": 0, "max": 100,
                "step": 1} for input_number, or {"name": "Mode",
                "options": ["a", "b"]} for input_select.
        """
        _check_domain(helper_domain)
        return await ws.ws_command(f"{helper_domain}/create", **fields)

    @mcp.tool(annotations=mutation("Update Helper", idempotent=True))
    async def update_helper(helper_domain: str, helper_id: str, fields: dict) -> dict:
        """Update a helper. Returns the updated helper.

        Args:
            helper_domain: The helper domain (see list_helpers).
            helper_id: The helper's id (the unique id, not the entity_id).
            fields: Domain-specific fields to change.
        """
        _check_domain(helper_domain)
        return await ws.ws_command(
            f"{helper_domain}/update", **{f"{helper_domain}_id": helper_id}, **fields
        )

    @mcp.tool(
        annotations=mutation("Delete Helper", destructive=True, idempotent=True)
    )
    async def delete_helper(
        helper_domain: str, helper_id: str, confirm: bool = False
    ) -> dict:
        """Delete a helper.

        Args:
            helper_domain: The helper domain (see list_helpers).
            helper_id: The helper's id (the unique id, not the entity_id).
            confirm: Must be true to perform this destructive operation.
        """
        _check_domain(helper_domain)
        if not confirm:
            raise HAToolError(
                "confirmation_required",
                f"set confirm=true to delete {helper_domain} {helper_id}",
            )
        return await ws.ws_command(
            f"{helper_domain}/delete", **{f"{helper_domain}_id": helper_id}
        )
