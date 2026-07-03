"""Write/mutation tools — available in read-write mode only."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ha_mcp.tools._annotations import mutation

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from ha_mcp.client import HAClient


def register(mcp: FastMCP, ha: HAClient) -> None:
    @mcp.tool(
        annotations=mutation("Set Entity State", destructive=True, idempotent=True)
    )
    async def set_entity_state(
        entity_id: str,
        state: str,
        attributes: dict | None = None,
    ) -> dict:
        """Set the state of an entity (creates it if it doesn't exist).

        Args:
            entity_id: The entity ID to set.
            state: The new state value.
            attributes: Optional attributes dict to set on the entity.
        """
        payload: dict = {"state": state}
        if attributes:
            payload["attributes"] = attributes
        return await ha.post(f"/api/states/{entity_id}", json=payload)

    @mcp.tool(annotations=mutation("Fire Event"))
    async def fire_event(
        event_type: str,
        event_data: dict | None = None,
    ) -> dict:
        """Fire an event on the Home Assistant event bus.

        Args:
            event_type: The event type to fire.
            event_data: Optional data to include with the event.
        """
        return await ha.post(f"/api/events/{event_type}", json=event_data or {})

    @mcp.tool(annotations=mutation("Handle Intent", destructive=True))
    async def handle_intent(
        name: str,
        data: dict | None = None,
    ) -> dict:
        """Handle an intent.

        Args:
            name: The intent name.
            data: Optional intent data.
        """
        payload: dict = {"name": name}
        if data:
            payload["data"] = data
        return await ha.post("/api/intent/handle", json=payload)

    @mcp.tool(
        annotations=mutation("Delete Entity State", destructive=True, idempotent=True)
    )
    async def delete_entity_state(entity_id: str) -> dict:
        """Delete an entity's state from Home Assistant.

        Args:
            entity_id: The entity ID to delete.
        """
        return await ha.delete(f"/api/states/{entity_id}")
