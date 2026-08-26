# SPDX-FileCopyrightText: 2026 Jeremy Beker <gothmog@confusticate.com>
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Shared MCP ToolAnnotations helpers.

Every tool targets a single, known Home Assistant instance, so openWorldHint is
False everywhere. Reads set readOnlyHint; mutations set destructive/idempotent
hints to match the tool's real effect.
"""

from __future__ import annotations

from mcp.types import ToolAnnotations


def read_only(title: str) -> ToolAnnotations:
    """Annotations for a tool that only reads state."""
    return ToolAnnotations(title=title, readOnlyHint=True, openWorldHint=False)


def mutation(
    title: str, *, destructive: bool = False, idempotent: bool = False
) -> ToolAnnotations:
    """Annotations for a tool that changes state."""
    return ToolAnnotations(
        title=title,
        readOnlyHint=False,
        destructiveHint=destructive,
        idempotentHint=idempotent,
        openWorldHint=False,
    )
