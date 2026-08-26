# SPDX-FileCopyrightText: 2026 Jeremy Beker <gothmog@confusticate.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Control tools — available in control-only and read-write modes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ha_mcp.tools._annotations import mutation

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from ha_mcp.client import HAClient


def register(mcp: FastMCP, ha: HAClient) -> None:
    @mcp.tool(annotations=mutation("Call Service", destructive=True))
    async def call_service(
        domain: str,
        service: str,
        service_data: dict | None = None,
        return_response: bool = False,
    ) -> dict | list:
        """Call a Home Assistant service.

        Args:
            domain: Service domain (e.g. 'light', 'switch', 'automation').
            service: Service name (e.g. 'turn_on', 'toggle').
            service_data: Optional data to pass to the service (e.g. entity_id, brightness).
            return_response: Whether to request a response from the service.
        """
        payload = service_data or {}
        if return_response:
            payload["return_response"] = True
        return await ha.post(f"/api/services/{domain}/{service}", json=payload)
