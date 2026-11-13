"""Owner-scoped audit records for deliberate destructive actions."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

import asyncpg


async def record_audit(
    db: asyncpg.Connection,
    owner_id: str,
    action: str,
    resource_type: str,
    resource_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Record bounded metadata only; callers must not pass raw evidence."""
    await db.execute(
        """
        INSERT INTO audit_log
            (owner_id, action, resource_type, resource_id, metadata)
        VALUES ($1, $2, $3, $4, $5::jsonb)
        """,
        owner_id,
        action,
        resource_type,
        resource_id,
        json.dumps(metadata or {}, separators=(",", ":")),
    )
