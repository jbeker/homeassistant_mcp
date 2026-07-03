"""Tests for wait_for_state (Group I) using stubbed clients."""

from __future__ import annotations

import asyncio

import pytest

from ha_mcp.tools import events
from ha_mcp.ws_client import WS_CLOSED, HAWebSocketError


class FakeMCP:
    def __init__(self) -> None:
        self.tools: dict[str, callable] = {}

    def tool(self, name=None, **kwargs):
        def deco(fn):
            self.tools[name or fn.__name__] = fn
            return fn

        return deco


class FakeHA:
    """Returns a fixed current state for any entity."""

    def __init__(self, state) -> None:
        self._state = state

    async def get(self, path):
        return {"entity_id": path.rsplit("/", 1)[-1], "state": self._state}


class FakeWS:
    """subscribe() hands back a pre-loaded queue; records unsubscribe."""

    def __init__(self, preload=None) -> None:
        self.queue: asyncio.Queue = asyncio.Queue()
        for item in preload or []:
            self.queue.put_nowait(item)
        self.subscribed = None
        self.unsubscribed = None

    async def subscribe(self, type, **fields):
        self.subscribed = (type, fields)
        return 7, self.queue

    async def unsubscribe(self, subscription_id):
        self.unsubscribed = subscription_id


def _wait_tool(ha, ws):
    mcp = FakeMCP()
    events.register(mcp, ha=ha, ws=ws)
    return mcp.tools["wait_for_state"]


async def test_already_at_target_returns_immediately():
    ws = FakeWS()
    tool = _wait_tool(FakeHA("on"), ws)
    out = await tool("light.kitchen", "on")
    assert out["matched"] is True
    assert out["already"] is True
    assert ws.unsubscribed == 7  # always cleans up


async def test_transition_matches():
    event = {"variables": {"trigger": {"to_state": {"state": "open"}}}}
    ws = FakeWS(preload=[event])
    tool = _wait_tool(FakeHA("closed"), ws)
    out = await tool("cover.garage", "open", timeout_seconds=2)
    assert out["matched"] is True
    assert out["state"] == "open"
    assert "already" not in out
    assert ws.subscribed[0] == "subscribe_trigger"
    assert ws.subscribed[1]["trigger"] == {
        "platform": "state",
        "entity_id": "cover.garage",
        "to": "open",
    }
    assert ws.unsubscribed == 7


async def test_timeout_returns_last_state():
    ws = FakeWS()  # no events arrive
    tool = _wait_tool(FakeHA("closed"), ws)
    out = await tool("cover.garage", "open", timeout_seconds=0.1)
    assert out["matched"] is False
    assert out["timed_out"] is True
    assert out["state"] == "closed"
    assert ws.unsubscribed == 7


async def test_connection_lost_raises():
    ws = FakeWS(preload=[WS_CLOSED])
    tool = _wait_tool(FakeHA("closed"), ws)
    with pytest.raises(HAWebSocketError) as exc:
        await tool("cover.garage", "open", timeout_seconds=2)
    assert exc.value.code == "connection_lost"
    assert ws.unsubscribed == 7  # cleaned up even on error
