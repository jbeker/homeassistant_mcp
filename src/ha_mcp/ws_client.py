"""Persistent WebSocket client for the Home Assistant WebSocket API.

The REST API does not expose the configuration/registry layer. Registry commands
(entity, area, device registries, helpers, labels, config entries, backups) are
only available over the WebSocket API at ``ws(s)://HOST:8123/api/websocket``.

This client maintains a single shared connection, performs the auth handshake,
and correlates requests with responses by an incrementing integer ``id``. A single
background reader task owns ``recv()`` and dispatches each reply to the awaiting
caller. Failures are *raised* (never returned as data) so FastMCP surfaces them as
real tool errors.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import websockets
from websockets.asyncio.client import ClientConnection, connect


class HAToolError(Exception):
    """A tool-level failure (validation, missing confirmation, HTTP error).

    Carries a stable ``code`` and a human-readable ``message`` so callers can
    distinguish failure modes. ``str()`` renders both.
    """

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class HAWebSocketError(HAToolError):
    """A failure originating from the Home Assistant WebSocket API."""


def _derive_ws_url(base_url: str) -> str:
    """Turn an http(s) base URL into the ws(s) WebSocket endpoint."""
    parts = urlsplit(base_url.rstrip("/"))
    scheme = "wss" if parts.scheme == "https" else "ws"
    return urlunsplit((scheme, parts.netloc, "/api/websocket", "", ""))


class HAWebSocketClient:
    """Single shared, lazily-connected Home Assistant WebSocket client."""

    def __init__(self, base_url: str, token: str, command_timeout: float = 30.0) -> None:
        self._ws_url = _derive_ws_url(base_url)
        self._token = token
        self._command_timeout = command_timeout

        self._ws: ClientConnection | None = None
        self._id = 0
        self._id_lock = asyncio.Lock()
        self._conn_lock = asyncio.Lock()
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None

    # -- connection lifecycle -------------------------------------------------

    async def _ensure_connected(self) -> None:
        """Connect and authenticate if not already connected. Idempotent."""
        if self._ws is not None:
            return
        async with self._conn_lock:
            # Re-check under the lock — another coroutine may have connected.
            if self._ws is not None:
                return

            ws = await connect(self._ws_url)
            try:
                # 1. Server sends auth_required.
                first = json.loads(await ws.recv())
                if first.get("type") != "auth_required":
                    raise HAWebSocketError(
                        "auth_handshake_failed",
                        f"expected auth_required, got {first.get('type')!r}",
                    )
                # 2/3. Send token, expect auth_ok.
                await ws.send(json.dumps({"type": "auth", "access_token": self._token}))
                result = json.loads(await ws.recv())
                if result.get("type") == "auth_invalid":
                    raise HAWebSocketError(
                        "auth_invalid", result.get("message", "invalid access token")
                    )
                if result.get("type") != "auth_ok":
                    raise HAWebSocketError(
                        "auth_handshake_failed",
                        f"expected auth_ok, got {result.get('type')!r}",
                    )
            except BaseException:
                await ws.close()
                raise

            # Command ids start at 1 on a fresh connection — reset the counter so
            # a reconnect restarts numbering (HA requires strictly increasing ids).
            self._id = 0
            self._ws = ws
            self._reader_task = asyncio.create_task(self._reader_loop(ws))

    async def _reader_loop(self, ws: ClientConnection) -> None:
        """Own ``recv()`` for one connection; dispatch results to pending futures."""
        try:
            async for raw in ws:
                msg = json.loads(raw)
                if msg.get("type") != "result":
                    continue  # ignore events/pong — subscriptions are out of scope
                fut = self._pending.get(msg.get("id"))
                if fut is None or fut.done():
                    continue
                if msg.get("success"):
                    fut.set_result(msg.get("result"))
                else:
                    err = msg.get("error") or {}
                    fut.set_exception(
                        HAWebSocketError(
                            err.get("code", "unknown_error"),
                            err.get("message", "command failed"),
                        )
                    )
        except Exception:
            pass  # connection dropped or unexpected error — handled in finally
        finally:
            self._ws = None
            self._fail_pending("connection_lost", "WebSocket connection closed")

    def _fail_pending(self, code: str, message: str) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(HAWebSocketError(code, message))
        self._pending.clear()

    async def _next_id(self) -> int:
        async with self._id_lock:
            self._id += 1
            return self._id

    # -- commands -------------------------------------------------------------

    async def ws_command(self, type: str, **fields: Any) -> Any:
        """Send one command, await the matching reply, and return its ``result``.

        Raises HAWebSocketError on a failed command, timeout, or dropped socket.
        """
        await self._ensure_connected()
        ws = self._ws
        if ws is None:
            raise HAWebSocketError("connection_lost", "WebSocket not connected")

        cid = await self._next_id()
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[cid] = fut
        try:
            await ws.send(json.dumps({"id": cid, "type": type, **fields}))
            return await asyncio.wait_for(fut, self._command_timeout)
        except asyncio.TimeoutError:
            raise HAWebSocketError("timeout", f"{type} timed out after {self._command_timeout}s")
        except websockets.ConnectionClosed:
            raise HAWebSocketError("connection_lost", f"connection closed during {type}")
        finally:
            self._pending.pop(cid, None)

    async def close(self) -> None:
        """Cancel the reader, close the socket, and fail any pending commands."""
        task, self._reader_task = self._reader_task, None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._fail_pending("connection_lost", "client closed")
