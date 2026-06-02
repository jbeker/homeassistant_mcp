"""Tests for the Home Assistant WebSocket client."""

from __future__ import annotations

import asyncio

import pytest

from ha_mcp.ws_client import (
    HAWebSocketClient,
    HAWebSocketError,
    _derive_ws_url,
)
from tests.conftest import VALID_TOKEN


def test_derive_ws_url():
    assert _derive_ws_url("http://ha.local:8123") == "ws://ha.local:8123/api/websocket"
    assert _derive_ws_url("https://ha.example.com:8123/") == "wss://ha.example.com:8123/api/websocket"


async def test_auth_and_command(ws_client, fake_server):
    fake_server.handler = lambda cmd: {"pong": cmd["type"]}
    result = await ws_client.ws_command("config/area_registry/list")
    assert result == {"pong": "config/area_registry/list"}
    # The auth frames carry no id; the first command must be id 1.
    assert fake_server.received[0]["id"] == 1


async def test_auth_invalid_raises(fake_server):
    fake_server.accept_auth = False
    client = HAWebSocketClient(fake_server.url, "wrong-token", command_timeout=2.0)
    with pytest.raises(HAWebSocketError) as exc:
        await client.ws_command("config/area_registry/list")
    assert exc.value.code == "auth_invalid"
    await client.close()


async def test_concurrent_commands_correlate(ws_client, fake_server):
    """Many in-flight commands must each receive their own reply."""

    def handler(cmd):
        return {"id_seen": cmd["id"], "n": cmd.get("n")}

    fake_server.handler = handler
    results = await asyncio.gather(
        *(ws_client.ws_command("ping", n=i) for i in range(10))
    )
    # Each result reflects the n it was sent with — proves correct correlation.
    assert sorted(r["n"] for r in results) == list(range(10))
    # Ids were strictly increasing and unique.
    ids = sorted(r["id_seen"] for r in results)
    assert ids == list(range(1, 11))


async def test_command_failure_surfaces_error(ws_client, fake_server):
    fake_server.handler = lambda cmd: {
        "success": False,
        "error": {"code": "not_found", "message": "Entity not found"},
    }
    with pytest.raises(HAWebSocketError) as exc:
        await ws_client.ws_command("config/entity_registry/get", entity_id="x.y")
    assert exc.value.code == "not_found"
    assert "Entity not found" in str(exc.value)


async def test_timeout(fake_server):
    fake_server.handler = lambda cmd: "__SILENT__"  # server never replies
    client = HAWebSocketClient(fake_server.url, VALID_TOKEN, command_timeout=0.3)
    with pytest.raises(HAWebSocketError) as exc:
        await client.ws_command("ping")
    assert exc.value.code == "timeout"
    await client.close()


async def test_reconnect_after_drop(ws_client, fake_server):
    """A mid-session drop fails the in-flight command, then the next call reconnects."""
    await ws_client.ws_command("ping")  # connect once
    assert ws_client._id == 1

    # The server drops the connection while handling this command (no reply).
    fake_server.handler = lambda cmd: "__CLOSE__"
    with pytest.raises(HAWebSocketError) as exc:
        await ws_client.ws_command("ping")
    assert exc.value.code == "connection_lost"

    # The same server is still listening — the next call lazily reconnects.
    fake_server.handler = lambda cmd: {"echo": cmd["type"]}
    result = await ws_client.ws_command("ping")
    assert result == {"echo": "ping"}
    # Id counter reset on the fresh connection — first command is id 1 again.
    assert ws_client._id == 1
