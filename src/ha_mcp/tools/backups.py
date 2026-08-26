# SPDX-FileCopyrightText: 2026 Jeremy Beker <gothmog@confusticate.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Backup tools over the WebSocket API — Group H.

Listing backups is a read; creating, deleting, and restoring are admin-only.
Delete and restore require ``confirm=True``. Restore is especially high risk: it
can interrupt the running instance.

The exact ``backup/generate`` and ``backup/restore`` options vary by Home
Assistant version, so creation/restore accept a passthrough ``options`` dict
rather than enumerating fields that may not exist on a given core.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ha_mcp.tools._annotations import mutation, read_only
from ha_mcp.ws_client import HAToolError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from ha_mcp.ws_client import HAWebSocketClient


def register(mcp: FastMCP, ws: HAWebSocketClient, admin: bool) -> None:
    @mcp.tool(annotations=read_only("List Backups"))
    async def list_backups() -> dict:
        """List available backups and backup-system status.

        Returns the backup info (backups list plus state such as whether a
        backup is currently running).
        """
        return await ws.ws_command("backup/info")

    if not admin:
        return

    @mcp.tool(annotations=mutation("Create Backup"))
    async def create_backup(options: dict | None = None) -> dict:
        """Create a new backup.

        Args:
            options: Version-specific generation options passed through to
                Home Assistant, e.g. {"name": "Pre-update", "agent_ids":
                ["backup.local"], "include_database": true}. Required fields
                (such as agent_ids on recent cores) depend on your version; an
                invalid set is surfaced as a structured error.
        """
        return await ws.ws_command("backup/generate", **(options or {}))

    @mcp.tool(
        annotations=mutation("Delete Backup", destructive=True, idempotent=True)
    )
    async def delete_backup(backup_id: str, confirm: bool = False) -> dict:
        """Delete a backup.

        Args:
            backup_id: The backup to delete.
            confirm: Must be true to perform this destructive operation.
        """
        if not confirm:
            raise HAToolError(
                "confirmation_required",
                f"set confirm=true to delete backup {backup_id}",
            )
        return await ws.ws_command("backup/delete", backup_id=backup_id)

    @mcp.tool(annotations=mutation("Restore Backup", destructive=True))
    async def restore_backup(
        backup_id: str, confirm: bool = False, options: dict | None = None
    ) -> dict:
        """Restore a backup. HIGH RISK — can interrupt the running instance.

        Restoring replaces current data with the backup's contents and typically
        restarts Home Assistant. Use with care.

        Args:
            backup_id: The backup to restore.
            confirm: Must be true to perform this high-risk operation.
            options: Version-specific restore options passed through, e.g.
                {"agent_id": "backup.local", "restore_database": true,
                "password": "..."}.
        """
        if not confirm:
            raise HAToolError(
                "confirmation_required",
                f"set confirm=true to restore backup {backup_id} "
                "(this can interrupt the running instance)",
            )
        return await ws.ws_command(
            "backup/restore", backup_id=backup_id, **(options or {})
        )
