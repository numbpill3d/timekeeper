"""Owner-scoped audit history."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth import CurrentUser
from ..db import get_db

router = APIRouter()
DB = Annotated[asyncpg.Connection, Depends(get_db)]


class AuditOut(BaseModel):
    id: UUID
    action: str
    resource_type: str
    resource_id: UUID | None
    metadata: dict
    created_at: datetime


@router.get("", response_model=list[AuditOut])
async def list_audit_log(
    user: CurrentUser,
    db: DB,
    limit: int = Query(50, ge=1, le=200),
) -> list[AuditOut]:
    rows = await db.fetch(
        """
        SELECT id, action, resource_type, resource_id, metadata, created_at
        FROM audit_log
        WHERE owner_id = $1
        ORDER BY created_at DESC, id DESC
        LIMIT $2
        """,
        user["sub"],
        limit,
    )
    return [AuditOut(**dict(row)) for row in rows]
