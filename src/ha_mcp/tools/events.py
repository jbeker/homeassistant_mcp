"""Bounded event/state-wait tool — Group I.

A request/response MCP tool cannot hold an open subscription, so the streaming
WebSocket commands (subscribe_events/subscribe_trigger/subscribe_entities) are
not exposed directly. ``wait_for_state`` is the bounded substitute: it opens a
short-lived ``subscribe_trigger`` stream, waits until the entity reaches the
target state or a timeout elapses, then closes the stream.

For historical event needs, use the existing get_logbook / get_history tools.
This tool is observational (no mutation), so it registers in every mode.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ha_mcp.tools._annotations import read_only
from ha_mcp.ws_client import WS_CLOSED, HAWebSocketError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from ha_mcp.client import HAClient
    from ha_mcp.ws_client import HAWebSocketClient


def _trigger_to_state(event: object) -> str | None:
    """Pull the new state out of a subscribe_trigger state-trigger event."""
    try:
        return event["variables"]["trigger"]["to_state"]["state"]  # type: ignore[index]
    except (KeyError, TypeError):
        return None


def register(mcp: FastMCP, ha: HAClient, ws: HAWebSocketClient) -> None:
    @mcp.tool(annotations=read_only("Wait For State"))
    async def wait_for_state(
        entity_id: str, target_state: str, timeout_seconds: float = 30.0
    ) -> dict:
        """Wait until an entity reaches a target state, or a timeout elapses.

        Opens a short-lived subscription, so it returns as soon as the entity
        transitions to target_state (it also returns immediately if the entity
        is already at target_state). On timeout it returns the last observed
        state instead of erroring.

        Args:
            entity_id: The entity to watch (e.g. 'cover.garage').
            target_state: The state to wait for (e.g. 'open').
            timeout_seconds: How long to wait before giving up (default 30).

        Returns:
            A dict with `matched` (bool), `entity_id`, `state` (the observed
            state), and either `already` (true if already at target) or
            `timed_out` (true if the wait expired).
        """
        # Subscribe first, then read the current state — this ordering means a
        # transition that happens while we check can't slip between the two.
        trigger = {"platform": "state", "entity_id": entity_id, "to": target_state}
        sub_id, queue = await ws.subscribe("subscribe_trigger", trigger=trigger)
        try:
            current = await ha.get(f"/api/states/{entity_id}")
            current_state = current.get("state") if isinstance(current, dict) else None
            if current_state == target_state:
                return {
                    "matched": True,
                    "entity_id": entity_id,
                    "state": target_state,
                    "already": True,
                }

            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout_seconds
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    return {
                        "matched": False,
                        "entity_id": entity_id,
                        "state": current_state,
                        "timed_out": True,
                    }
                try:
                    event = await asyncio.wait_for(queue.get(), remaining)
                except asyncio.TimeoutError:
                    return {
                        "matched": False,
                        "entity_id": entity_id,
                        "state": current_state,
                        "timed_out": True,
                    }
                if event is WS_CLOSED:
                    raise HAWebSocketError(
                        "connection_lost", "WebSocket closed while waiting for state"
                    )
                return {
                    "matched": True,
                    "entity_id": entity_id,
                    "state": _trigger_to_state(event) or target_state,
                }
        finally:
            await ws.unsubscribe(sub_id)
