"""FastMCP server factory with mode-based tool registration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from ha_mcp.client import HAClient
from ha_mcp.tools import read, control, write, registry, config_edit
from ha_mcp.ws_client import HAWebSocketClient


def create_server(mode: str, ha_url: str, ha_token: str) -> FastMCP:
    """Create a FastMCP server with tools registered according to the access mode."""

    # Create clients eagerly — both connect lazily on first use.
    ha_client = HAClient(ha_url, ha_token)
    ws_client = HAWebSocketClient(ha_url, ha_token)

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
        try:
            yield {}
        finally:
            for client in (ws_client, ha_client):
                try:
                    await client.close()
                except Exception:
                    pass

    mcp = FastMCP(
        "Home Assistant",
        instructions="MCP server for Home Assistant REST API",
        lifespan=lifespan,
    )

    # 'admin' is a superset of 'read-write' plus registry/config mutation tools.
    is_admin = mode == "admin"

    # Register tools based on mode — closures capture the clients
    read.register(mcp, ha_client)

    if mode in ("control-only", "read-write", "admin"):
        control.register(mcp, ha_client)

    if mode in ("read-write", "admin"):
        write.register(mcp, ha_client)

    # Registry/config reads register in every mode; mutations gate behind admin.
    registry.register(mcp, ha_client, ws_client, admin=is_admin)
    config_edit.register(mcp, ha_client, admin=is_admin)

    return mcp
