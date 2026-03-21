"""FastMCP server factory with mode-based tool registration."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server.fastmcp import FastMCP

from ha_mcp.client import HAClient
from ha_mcp.tools import read, control, write


def create_server(mode: str, ha_url: str, ha_token: str) -> FastMCP:
    """Create a FastMCP server with tools registered according to the access mode."""

    # Create client eagerly — httpx.AsyncClient is lazy and doesn't connect until used.
    ha_client = HAClient(ha_url, ha_token)

    @asynccontextmanager
    async def lifespan(server: FastMCP) -> AsyncIterator[dict]:
        try:
            yield {}
        finally:
            await ha_client.close()

    mcp = FastMCP(
        "Home Assistant",
        instructions="MCP server for Home Assistant REST API",
        lifespan=lifespan,
    )

    # Register tools based on mode — closures capture ha_client
    read.register(mcp, ha_client)

    if mode in ("control-only", "read-write"):
        control.register(mcp, ha_client)

    if mode == "read-write":
        write.register(mcp, ha_client)

    return mcp
