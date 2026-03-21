"""CLI entry point for the Home Assistant MCP server."""

import os
import sys

import click
from dotenv import load_dotenv

from ha_mcp.server import create_server


@click.command()
@click.option(
    "--mode",
    type=click.Choice(["read-only", "control-only", "read-write"]),
    default="read-only",
    help="Access mode controlling which tools are exposed.",
)
@click.option(
    "--transport",
    type=click.Choice(["stdio", "sse", "streamable-http"]),
    default="stdio",
    help="MCP transport to use.",
)
@click.option("--host", default="127.0.0.1", help="Host for HTTP transports.")
@click.option("--port", default=8000, type=int, help="Port for HTTP transports.")
def main(mode: str, transport: str, host: str, port: int) -> None:
    """Home Assistant MCP Server."""
    load_dotenv()

    ha_url = os.environ.get("HA_URL")
    ha_token = os.environ.get("HA_TOKEN")

    if not ha_url or not ha_token:
        click.echo("Error: HA_URL and HA_TOKEN environment variables are required.", err=True)
        click.echo("Set them in a .env file or export them in your shell.", err=True)
        sys.exit(1)

    server = create_server(mode, ha_url, ha_token)
    server.settings.host = host
    server.settings.port = port

    server.run(transport=transport)


if __name__ == "__main__":
    main()
