"""Person management routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUser
from ..db import get_db

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]


class PersonOut(BaseModel):
    id: UUID
    label: str
    is_known: bool
    appearance_tags: list[str]
    retention_days: int
    last_seen_at: datetime | None
    created_at: datetime
    event_count: int


class PersonUpdate(BaseModel):
    label: str | None = None
    is_known: bool | None = None


@router.get("", response_model=list[PersonOut])
async def list_persons(user: CurrentUser, db: DB) -> list[PersonOut]:
    rows = await db.fetch(
        """
        SELECT p.*,
               COUNT(e.id) AS event_count
        FROM persons p
        LEFT JOIN events e ON e.person_id = p.id
        WHERE p.owner_id = $1
        GROUP BY p.id
        ORDER BY p.last_seen_at DESC NULLS LAST, p.created_at DESC
        """,
        user["sub"],
    )
    return [PersonOut(**dict(r)) for r in rows]


@router.get("/{person_id}", response_model=PersonOut)
async def get_person(person_id: UUID, user: CurrentUser, db: DB) -> PersonOut:
    row = await db.fetchrow(
        """
        SELECT p.*, COUNT(e.id) AS event_count
        FROM persons p
        LEFT JOIN events e ON e.person_id = p.id
        WHERE p.id = $1 AND p.owner_id = $2
        GROUP BY p.id
        """,
        person_id,
        user["sub"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="person not found")
    return PersonOut(**dict(row))


@router.patch("/{person_id}", response_model=PersonOut)
async def update_person(
    person_id: UUID, req: PersonUpdate, user: CurrentUser, db: DB
) -> PersonOut:
    _ALLOWED = {"label", "is_known"}
    updates: dict = {}
    if req.label is not None:
        updates["label"] = req.label
    if req.is_known is not None:
        updates["is_known"] = req.is_known

    if not updates:
        return await get_person(person_id, user, db)

    assert set(updates) <= _ALLOWED
    sets = ", ".join(f"{col} = ${i + 3}" for i, col in enumerate(updates))
    result = await db.execute(
        f"UPDATE persons SET {sets} WHERE id = $1 AND owner_id = $2",
        person_id,
        user["sub"],
        *updates.values(),
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="person not found")
    return await get_person(person_id, user, db)


@router.delete("/{person_id}", status_code=204)
async def delete_person(
    person_id: UUID, user: CurrentUser, db: DB
) -> None:
    result = await db.execute(
        "DELETE FROM persons WHERE id = $1 AND owner_id = $2",
        person_id,
        user["sub"],
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="person not found")
