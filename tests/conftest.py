"""Shared fixtures: a fake Home Assistant WebSocket server.

The fake server performs the real auth handshake and then dispatches commands to
a per-test handler, so the WebSocket client can be exercised end-to-end without a
live Home Assistant.
"""

from __future__ import annotations

import asyncio
import json

import pytest
import pytest_asyncio
from websockets.asyncio.server import serve

from ha_mcp.ws_client import HAWebSocketClient

VALID_TOKEN = "test-token"


class FakeHAServer:
    """A minimal HA WebSocket server driven by a command handler callback."""

    def __init__(self, handler=None, *, accept_auth: bool = True) -> None:
        # handler(command: dict) -> dict result body (the "result" field), or it may
        # return a full frame dict containing "success"/"error" to control the reply.
        self.handler = handler or (lambda cmd: {"echo": cmd["type"]})
        self.accept_auth = accept_auth
        self.received: list[dict] = []
        self._server = None
        self.port: int | None = None

    async def start(self) -> None:
        self._server = await serve(self._serve, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def _serve(self, ws) -> None:
        await ws.send(json.dumps({"type": "auth_required"}))
        auth = json.loads(await ws.recv())
        if not self.accept_auth or auth.get("access_token") != VALID_TOKEN:
            await ws.send(json.dumps({"type": "auth_invalid", "message": "bad token"}))
            return
        await ws.send(json.dumps({"type": "auth_ok"}))
        try:
            async for raw in ws:
                cmd = json.loads(raw)
                self.received.append(cmd)
                body = self.handler(cmd)
                if body == "__SILENT__":
                    continue  # never reply — exercises the per-command timeout
                if body == "__CLOSE__":
                    break  # drop the connection mid-session
                if isinstance(body, dict) and ("success" in body or "error" in body):
                    frame = {"id": cmd["id"], "type": "result", **body}
                else:
                    frame = {"id": cmd["id"], "type": "result", "success": True, "result": body}
                await ws.send(json.dumps(frame))
        except Exception:
            pass


@pytest_asyncio.fixture
async def fake_server():
    server = FakeHAServer()
    await server.start()
    yield server
    await server.stop()


@pytest_asyncio.fixture
async def ws_client(fake_server):
    client = HAWebSocketClient(fake_server.url, VALID_TOKEN, command_timeout=2.0)
    yield client
    await client.close()
