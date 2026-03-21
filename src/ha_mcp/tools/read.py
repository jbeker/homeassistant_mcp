"""Read-only tools — available in all access modes."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from ha_mcp.client import HAClient


def register(mcp: FastMCP, ha: HAClient) -> None:
    @mcp.tool()
    async def check_api() -> dict:
        """Check if the Home Assistant API is running."""
        return await ha.get("/api/")

    @mcp.tool()
    async def get_config() -> dict:
        """Get Home Assistant configuration."""
        return await ha.get("/api/config")

    @mcp.tool()
    async def list_components() -> list:
        """List all loaded Home Assistant components."""
        return await ha.get("/api/components")

    @mcp.tool()
    async def list_events() -> list:
        """List all available event types."""
        return await ha.get("/api/events")

    @mcp.tool()
    async def list_services() -> list:
        """List all available services."""
        return await ha.get("/api/services")

    @mcp.tool()
    async def get_all_states() -> list:
        """Get states of all entities."""
        return await ha.get("/api/states")

    @mcp.tool()
    async def get_entity_state(entity_id: str) -> dict:
        """Get the state of a specific entity.

        Args:
            entity_id: The entity ID (e.g. 'light.living_room').
        """
        return await ha.get(f"/api/states/{entity_id}")

    @mcp.tool()
    async def get_error_log() -> str:
        """Get the Home Assistant error log."""
        return await ha.get("/api/error_log")

    @mcp.tool()
    async def get_camera_image(entity_id: str) -> str:
        """Get a camera image as base64-encoded PNG.

        Args:
            entity_id: The camera entity ID (e.g. 'camera.front_door').
        """
        raw = await ha.get_raw(f"/api/camera_proxy/{entity_id}")
        return base64.b64encode(raw).decode()

    @mcp.tool()
    async def list_calendars() -> list:
        """List all calendar entities."""
        return await ha.get("/api/calendars")

    @mcp.tool()
    async def get_calendar_events(entity_id: str, start: str, end: str) -> list:
        """Get events from a calendar within a time range.

        Args:
            entity_id: The calendar entity ID.
            start: Start datetime in ISO 8601 format.
            end: End datetime in ISO 8601 format.
        """
        return await ha.get(
            f"/api/calendars/{entity_id}",
            params={"start": start, "end": end},
        )

    @mcp.tool()
    async def get_history(
        timestamp: str,
        entity_id: str | None = None,
        end_time: str | None = None,
    ) -> list:
        """Get state history for a period.

        Args:
            timestamp: Start time in ISO 8601 format.
            entity_id: Optional entity ID to filter by.
            end_time: Optional end time in ISO 8601 format.
        """
        params: dict = {}
        if entity_id:
            params["filter_entity_id"] = entity_id
        if end_time:
            params["end_time"] = end_time
        return await ha.get(f"/api/history/period/{timestamp}", params=params)

    @mcp.tool()
    async def get_logbook(
        timestamp: str,
        entity_id: str | None = None,
        end_time: str | None = None,
    ) -> list:
        """Get logbook entries for a period.

        Args:
            timestamp: Start time in ISO 8601 format.
            entity_id: Optional entity ID to filter by.
            end_time: Optional end time in ISO 8601 format.
        """
        params: dict = {}
        if entity_id:
            params["entity"] = entity_id
        if end_time:
            params["end_time"] = end_time
        return await ha.get(f"/api/logbook/{timestamp}", params=params)

    @mcp.tool()
    async def render_template(template: str) -> str:
        """Render a Jinja2 template against Home Assistant state.

        Args:
            template: Jinja2 template string to render.
        """
        return await ha.post("/api/template", json={"template": template})

    @mcp.tool()
    async def check_config() -> dict:
        """Check the Home Assistant configuration for errors."""
        return await ha.post("/api/config/core/check_config")
