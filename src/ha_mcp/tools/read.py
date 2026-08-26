# SPDX-FileCopyrightText: 2026 Jeremy Beker <gothmog@confusticate.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Read-only tools — available in all access modes."""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from ha_mcp.tools._annotations import read_only

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from ha_mcp.client import HAClient


def register(mcp: FastMCP, ha: HAClient) -> None:
    @mcp.tool(annotations=read_only("Check API"))
    async def check_api() -> dict:
        """Check if the Home Assistant API is running."""
        return await ha.get("/api/")

    @mcp.tool(annotations=read_only("Get Configuration"))
    async def get_config() -> dict:
        """Get Home Assistant configuration."""
        return await ha.get("/api/config")

    @mcp.tool(annotations=read_only("List Components"))
    async def list_components() -> list:
        """List all loaded Home Assistant components."""
        return await ha.get("/api/components")

    @mcp.tool(annotations=read_only("List Event Types"))
    async def list_events() -> list:
        """List all available event types."""
        return await ha.get("/api/events")

    @mcp.tool(annotations=read_only("List Areas"))
    async def list_areas() -> list:
        """List all areas (rooms/zones) defined in Home Assistant."""
        template = (
            '[{% for area_id in areas() %}'
            '{"area_id":"{{ area_id }}",'
            '"name":"{{ area_name(area_id) | replace(\'"\', \'\\\\"\') }}"}'
            '{% if not loop.last %},{% endif %}'
            '{% endfor %}]'
        )
        result = await ha.post("/api/template", json={"template": template})
        return json.loads(result)

    @mcp.tool(annotations=read_only("List Devices"))
    async def list_devices(area_id: str | None = None) -> list:
        """List all registered devices.

        Args:
            area_id: Optional area ID to filter devices by location.
        """
        area_filter = f"['{area_id}']" if area_id else "areas()"
        template = (
            '{%- set ns = namespace(first=true) -%}['
            '{%- for aid in ' + area_filter + ' -%}'
            '{%- for dev_id in area_devices(aid) -%}'
            '{%- if not ns.first -%},{%- endif -%}'
            '{%- set ns.first = false -%}'
            '{"device_id":"{{ dev_id }}",'
            '"name":"{{ device_attr(dev_id, "name") | replace(\'"\', \'\\\\"\') }}",'
            '"area_id":"{{ device_attr(dev_id, "area_id") }}",'
            '"manufacturer":"{{ device_attr(dev_id, "manufacturer") | replace(\'"\', \'\\\\"\') }}",'
            '"model":"{{ device_attr(dev_id, "model") | replace(\'"\', \'\\\\"\') }}"}'
            '{%- endfor -%}'
            '{%- endfor -%}]'
        )
        result = await ha.post("/api/template", json={"template": template})
        return json.loads(result)

    @mcp.tool(annotations=read_only("List Services"))
    async def list_services(domain: str | None = None) -> list:
        """List all available services.

        Args:
            domain: Optional domain filter (e.g. 'light', 'climate').
        """
        services = await ha.get("/api/services")
        if domain:
            services = [s for s in services if s.get("domain") == domain]
        return services

    @mcp.tool(annotations=read_only("List Entities"))
    async def list_entities(
        domain: str | None = None,
        name_filter: str | None = None,
    ) -> list[dict]:
        """List all entities with minimal info for discovery.

        Returns entity_id, friendly name, and current state value (no attributes).
        Use this instead of get_all_states to avoid overwhelming context.

        Args:
            domain: Optional domain filter (e.g. 'sensor', 'light').
            name_filter: Optional case-insensitive substring match on friendly name.
        """
        states = await ha.get("/api/states")
        results = []
        for s in states:
            eid = s["entity_id"]
            if domain and not eid.startswith(f"{domain}."):
                continue
            friendly = s.get("attributes", {}).get("friendly_name", "")
            if name_filter and name_filter.lower() not in friendly.lower():
                continue
            results.append({
                "entity_id": eid,
                "name": friendly,
                "state": s.get("state", ""),
            })
        return results

    @mcp.tool(annotations=read_only("Get Entity States"))
    async def get_entity_states(entity_ids: list[str]) -> list[dict]:
        """Get full state for multiple entities in one call.

        Args:
            entity_ids: List of entity IDs to fetch (e.g. ['sensor.temp', 'light.kitchen']).
        """
        results = await asyncio.gather(
            *(ha.get(f"/api/states/{eid}") for eid in entity_ids),
            return_exceptions=True,
        )
        out = []
        for eid, result in zip(entity_ids, results):
            if isinstance(result, Exception):
                out.append({"entity_id": eid, "error": str(result)})
            else:
                out.append(result)
        return out

    @mcp.tool(annotations=read_only("Get All States"))
    async def get_all_states(domain: str | None = None) -> list:
        """Get states of all entities.

        Args:
            domain: Optional domain filter (e.g. 'sensor', 'light') to limit results.
        """
        states = await ha.get("/api/states")
        if domain:
            states = [s for s in states if s["entity_id"].startswith(f"{domain}.")]
        return states

    @mcp.tool(annotations=read_only("Get Entity State"))
    async def get_entity_state(entity_id: str) -> dict:
        """Get the state of a specific entity.

        Args:
            entity_id: The entity ID (e.g. 'light.living_room').
        """
        return await ha.get(f"/api/states/{entity_id}")

    @mcp.tool(annotations=read_only("Get Error Log"))
    async def get_error_log(lines: int | None = None) -> str:
        """Get the Home Assistant error log.

        Args:
            lines: Optional number of lines to return from the end of the log.
                   When omitted, returns the full log.
        """
        log = await ha.get("/api/error_log")
        if lines is not None:
            log_lines = log.rstrip("\n").split("\n")
            return "\n".join(log_lines[-lines:])
        return log

    @mcp.tool(annotations=read_only("Get Camera Image"))
    async def get_camera_image(entity_id: str) -> str:
        """Get a camera image as base64-encoded PNG.

        Args:
            entity_id: The camera entity ID (e.g. 'camera.front_door').
        """
        raw = await ha.get_raw(f"/api/camera_proxy/{entity_id}")
        return base64.b64encode(raw).decode()

    @mcp.tool(annotations=read_only("List Calendars"))
    async def list_calendars() -> list:
        """List all calendar entities."""
        return await ha.get("/api/calendars")

    @mcp.tool(annotations=read_only("Get Calendar Events"))
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

    @mcp.tool(annotations=read_only("Get History"))
    async def get_history(
        timestamp: str | None = None,
        entity_id: str | None = None,
        end_time: str | None = None,
    ) -> list:
        """Get state history for a period.

        Args:
            timestamp: Start time in ISO 8601 format. Defaults to 1 hour ago.
            entity_id: Entity ID(s) to filter by. Supports comma-separated values
                       (e.g. 'sensor.temp,sensor.humidity'). Strongly recommended
                       to avoid pulling history for all entities.
            end_time: Optional end time in ISO 8601 format.
        """
        if timestamp is None:
            timestamp = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        params: dict = {}
        if entity_id:
            params["filter_entity_id"] = entity_id
        if end_time:
            params["end_time"] = end_time
        return await ha.get(f"/api/history/period/{timestamp}", params=params)

    @mcp.tool(annotations=read_only("Get Logbook"))
    async def get_logbook(
        timestamp: str | None = None,
        entity_id: str | None = None,
        end_time: str | None = None,
    ) -> list:
        """Get logbook entries for a period.

        Args:
            timestamp: Start time in ISO 8601 format. Defaults to 1 hour ago.
            entity_id: Entity ID to filter by. Strongly recommended to avoid
                       pulling logbook entries for all entities.
            end_time: Optional end time in ISO 8601 format.
        """
        if timestamp is None:
            timestamp = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        params: dict = {}
        if entity_id:
            params["entity"] = entity_id
        if end_time:
            params["end_time"] = end_time
        return await ha.get(f"/api/logbook/{timestamp}", params=params)

    @mcp.tool(annotations=read_only("Render Template"))
    async def render_template(template: str) -> str:
        """Render a Jinja2 template against Home Assistant state.

        Args:
            template: Jinja2 template string to render.
        """
        return await ha.post("/api/template", json={"template": template})

    @mcp.tool(annotations=read_only("Check Configuration"))
    async def check_config() -> dict:
        """Check the Home Assistant configuration for errors."""
        return await ha.post("/api/config/core/check_config")
