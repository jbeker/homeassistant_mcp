# SPDX-FileCopyrightText: 2026 Jeremy Beker <gothmog@confusticate.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Registry tools over the WebSocket API — entity (A), area (C), device (D).

Read tools (list/get) register in every mode. Mutating tools register only when
``admin`` is true. Destructive operations require ``confirm=True``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ha_mcp.tools._annotations import mutation, read_only
from ha_mcp.ws_client import HAToolError

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

    from ha_mcp.client import HAClient
    from ha_mcp.ws_client import HAWebSocketClient


_ENTITY_ID_RE = re.compile(r"^[a-z0-9_]+\.[a-z0-9_]+$")


def register(mcp: FastMCP, ha: HAClient, ws: HAWebSocketClient, admin: bool) -> None:
    # -- Group A: entity registry (reads) ------------------------------------

    @mcp.tool(annotations=read_only("List Entity Registry"))
    async def list_entity_registry(
        domain: str | None = None,
        area_id: str | None = None,
    ) -> list[dict]:
        """List entity registry entries (richer than list_entities).

        Returns entries including entity_id, name, original_name, platform,
        unique_id, device_id, area_id, disabled_by, hidden_by, and entity_category.

        Args:
            domain: Optional domain filter (e.g. 'sensor', 'light').
            area_id: Optional area filter (matched against the entry's area_id).
        """
        entries = await ws.ws_command("config/entity_registry/list")
        if domain:
            entries = [e for e in entries if e.get("entity_id", "").startswith(f"{domain}.")]
        if area_id:
            entries = [e for e in entries if e.get("area_id") == area_id]
        return entries

    @mcp.tool(annotations=read_only("Get Entity Registry Entry"))
    async def get_entity_registry_entry(entity_id: str) -> dict:
        """Get the full entity registry entry, including unique_id.

        Args:
            entity_id: The entity ID (e.g. 'sensor.living_room_temp').
        """
        return await ws.ws_command("config/entity_registry/get", entity_id=entity_id)

    # -- Group F: label & category registries (reads) ------------------------

    @mcp.tool(annotations=read_only("List Labels"))
    async def list_labels() -> list[dict]:
        """List all labels (each with label_id, name, color, icon, description)."""
        return await ws.ws_command("config/label_registry/list")

    @mcp.tool(annotations=read_only("List Categories"))
    async def list_categories(scope: str) -> list[dict]:
        """List categories for a scope.

        Args:
            scope: The category scope (e.g. 'automation', 'script', 'todo').
        """
        return await ws.ws_command("config/category_registry/list", scope=scope)

    if not admin:
        return

    # -- Group A: entity registry (mutations) --------------------------------

    @mcp.tool(
        annotations=mutation("Update Entity Registry Entry", idempotent=True)
    )
    async def update_entity_registry_entry(entity_id: str, updates: dict) -> dict:
        """Update entity registry fields.

        Args:
            entity_id: The entity ID to update.
            updates: Fields to change. Any of: name, icon, area_id, new_entity_id,
                disabled_by, hidden_by, labels, aliases. Use new_entity_id to rename
                (prefer the rename_entity tool, which validates the target).
        """
        return await ws.ws_command(
            "config/entity_registry/update", entity_id=entity_id, **updates
        )

    @mcp.tool(annotations=mutation("Rename Entity"))
    async def rename_entity(entity_id: str, new_entity_id: str) -> dict:
        """Change an entity's entity_id. History migrates automatically.

        The domain must stay the same and the target id must not already exist.

        Args:
            entity_id: The current entity ID.
            new_entity_id: The desired entity ID (must match <domain>.<object_id>).
        """
        if not _ENTITY_ID_RE.match(new_entity_id):
            raise HAToolError(
                "invalid_entity_id",
                f"{new_entity_id!r} must match ^[a-z0-9_]+\\.[a-z0-9_]+$",
            )
        if entity_id.split(".")[0] != new_entity_id.split(".")[0]:
            raise HAToolError(
                "domain_change_forbidden",
                "the domain of an entity cannot be changed by a rename",
            )
        existing = await ws.ws_command("config/entity_registry/list")
        clash = next((e for e in existing if e.get("entity_id") == new_entity_id), None)
        if clash is not None:
            raise HAToolError(
                "target_exists",
                f"{new_entity_id} already exists: {clash}",
            )
        return await ws.ws_command(
            "config/entity_registry/update",
            entity_id=entity_id,
            new_entity_id=new_entity_id,
        )

    @mcp.tool(
        annotations=mutation(
            "Remove Entity Registry Entry", destructive=True, idempotent=True
        )
    )
    async def remove_entity_registry_entry(entity_id: str, confirm: bool = False) -> dict:
        """Remove an entity registry entry (only if the platform allows it).

        Args:
            entity_id: The entity ID to remove.
            confirm: Must be true to perform this destructive operation.
        """
        if not confirm:
            raise HAToolError(
                "confirmation_required",
                f"set confirm=true to remove registry entry {entity_id}",
            )
        return await ws.ws_command("config/entity_registry/remove", entity_id=entity_id)

    # -- Group C: area registry (mutations) ----------------------------------

    @mcp.tool(annotations=mutation("Create Area"))
    async def create_area(
        name: str,
        icon: str | None = None,
        floor_id: str | None = None,
        aliases: list[str] | None = None,
        labels: list[str] | None = None,
    ) -> dict:
        """Create an area. Returns the created area including area_id.

        Args:
            name: Area name.
            icon: Optional MDI icon (e.g. 'mdi:sofa').
            floor_id: Optional floor to place the area on.
            aliases: Optional voice-assistant aliases.
            labels: Optional label ids to attach.
        """
        fields = _drop_none(icon=icon, floor_id=floor_id, aliases=aliases, labels=labels)
        return await ws.ws_command("config/area_registry/create", name=name, **fields)

    @mcp.tool(annotations=mutation("Update Area", idempotent=True))
    async def update_area(
        area_id: str,
        name: str | None = None,
        icon: str | None = None,
        picture: str | None = None,
        floor_id: str | None = None,
        aliases: list[str] | None = None,
        labels: list[str] | None = None,
    ) -> dict:
        """Update an area. Renaming does not affect entity ids or history.

        Args:
            area_id: The area to update.
            name: New name.
            icon: New MDI icon.
            picture: New picture URL.
            floor_id: New floor id.
            aliases: New voice-assistant aliases.
            labels: New label ids.
        """
        fields = _drop_none(
            name=name, icon=icon, picture=picture, floor_id=floor_id,
            aliases=aliases, labels=labels,
        )
        return await ws.ws_command("config/area_registry/update", area_id=area_id, **fields)

    @mcp.tool(
        annotations=mutation("Delete Area", destructive=True, idempotent=True)
    )
    async def delete_area(area_id: str, confirm: bool = False) -> dict:
        """Delete an area.

        Args:
            area_id: The area to delete.
            confirm: Must be true to perform this destructive operation.
        """
        if not confirm:
            raise HAToolError(
                "confirmation_required", f"set confirm=true to delete area {area_id}"
            )
        return await ws.ws_command("config/area_registry/delete", area_id=area_id)

    # -- Group D: device registry (mutations) --------------------------------

    @mcp.tool(annotations=mutation("Update Device", idempotent=True))
    async def update_device(
        device_id: str,
        name_by_user: str | None = None,
        area_id: str | None = None,
        disabled: bool | None = None,
        labels: list[str] | None = None,
    ) -> dict:
        """Update a device registry entry.

        Args:
            device_id: The device to update.
            name_by_user: Override the device name without altering the
                integration-supplied name.
            area_id: Reassign the device's area. Moves its entities unless an
                entity sets its own area override.
            disabled: Disable (true) or enable (false) the device.
            labels: Label ids to attach.
        """
        fields = _drop_none(name_by_user=name_by_user, area_id=area_id, labels=labels)
        if disabled is not None:
            fields["disabled_by"] = "user" if disabled else None
        return await ws.ws_command(
            "config/device_registry/update", device_id=device_id, **fields
        )

    # -- Group F: label registry (mutations) ---------------------------------

    @mcp.tool(annotations=mutation("Create Label"))
    async def create_label(
        name: str,
        color: str | None = None,
        icon: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Create a label. Returns the created label including label_id.

        Assign labels to entities/devices via update_entity_registry_entry /
        update_device.

        Args:
            name: Label name.
            color: Optional color (e.g. 'primary', 'red').
            icon: Optional MDI icon.
            description: Optional description.
        """
        fields = _drop_none(color=color, icon=icon, description=description)
        return await ws.ws_command("config/label_registry/create", name=name, **fields)

    @mcp.tool(annotations=mutation("Update Label", idempotent=True))
    async def update_label(
        label_id: str,
        name: str | None = None,
        color: str | None = None,
        icon: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Update a label.

        Args:
            label_id: The label to update.
            name: New name.
            color: New color.
            icon: New MDI icon.
            description: New description.
        """
        fields = _drop_none(name=name, color=color, icon=icon, description=description)
        return await ws.ws_command(
            "config/label_registry/update", label_id=label_id, **fields
        )

    @mcp.tool(
        annotations=mutation("Delete Label", destructive=True, idempotent=True)
    )
    async def delete_label(label_id: str, confirm: bool = False) -> dict:
        """Delete a label.

        Args:
            label_id: The label to delete.
            confirm: Must be true to perform this destructive operation.
        """
        if not confirm:
            raise HAToolError(
                "confirmation_required", f"set confirm=true to delete label {label_id}"
            )
        return await ws.ws_command("config/label_registry/delete", label_id=label_id)

    # -- Group F: category registry (mutations) ------------------------------

    @mcp.tool(annotations=mutation("Create Category"))
    async def create_category(
        scope: str, name: str, icon: str | None = None
    ) -> dict:
        """Create a category within a scope. Returns the created category.

        Args:
            scope: The category scope (e.g. 'automation', 'script', 'todo').
            name: Category name.
            icon: Optional MDI icon.
        """
        fields = _drop_none(icon=icon)
        return await ws.ws_command(
            "config/category_registry/create", scope=scope, name=name, **fields
        )

    @mcp.tool(annotations=mutation("Update Category", idempotent=True))
    async def update_category(
        scope: str,
        category_id: str,
        name: str | None = None,
        icon: str | None = None,
    ) -> dict:
        """Update a category.

        Args:
            scope: The category scope.
            category_id: The category to update.
            name: New name.
            icon: New MDI icon.
        """
        fields = _drop_none(name=name, icon=icon)
        return await ws.ws_command(
            "config/category_registry/update",
            scope=scope,
            category_id=category_id,
            **fields,
        )

    @mcp.tool(
        annotations=mutation("Delete Category", destructive=True, idempotent=True)
    )
    async def delete_category(
        scope: str, category_id: str, confirm: bool = False
    ) -> dict:
        """Delete a category.

        Args:
            scope: The category scope.
            category_id: The category to delete.
            confirm: Must be true to perform this destructive operation.
        """
        if not confirm:
            raise HAToolError(
                "confirmation_required",
                f"set confirm=true to delete category {category_id}",
            )
        return await ws.ws_command(
            "config/category_registry/delete", scope=scope, category_id=category_id
        )


def _drop_none(**kwargs):
    """Return only the keyword arguments that are not None."""
    return {k: v for k, v in kwargs.items() if v is not None}
