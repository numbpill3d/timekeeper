"""Person management routes."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from ..auth import CurrentUser
from ..db import get_db

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]


def _person_out(row: asyncpg.Record | dict) -> PersonOut:
    data = dict(row)
    # Keep the public contract stable for legacy rows and database adapters
    # that return NULL for the nullable historical array column.
    data["appearance_tags"] = data.get("appearance_tags") or []
    return PersonOut(**data)


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
    label: str | None = Field(default=None, min_length=1, max_length=120)
    is_known: bool | None = None

    @field_validator("label")
    @classmethod
    def _strip_label(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else None
        if value == "":
            raise ValueError("label cannot be empty")
        return value


@router.get("", response_model=list[PersonOut])
async def list_persons(user: CurrentUser, db: DB) -> list[PersonOut]:
    rows = await db.fetch(
        """
        SELECT p.*,
               COALESCE(p.appearance_tags, ARRAY[]::text[]) AS appearance_tags,
               COUNT(e.id) AS event_count
        FROM persons p
        LEFT JOIN events e ON e.person_id = p.id
             AND e.camera_id IN (SELECT id FROM cameras WHERE owner_id = $1)
        WHERE p.owner_id = $1
        GROUP BY p.id
        ORDER BY p.last_seen_at DESC NULLS LAST, p.created_at DESC, p.id DESC
        """,
        user["sub"],
    )
    return [_person_out(r) for r in rows]


@router.get("/{person_id}", response_model=PersonOut)
async def get_person(person_id: UUID, user: CurrentUser, db: DB) -> PersonOut:
    row = await db.fetchrow(
        """
        SELECT p.*,
               COALESCE(p.appearance_tags, ARRAY[]::text[]) AS appearance_tags,
               COUNT(e.id) AS event_count
        FROM persons p
        LEFT JOIN events e ON e.person_id = p.id
             AND e.camera_id IN (SELECT id FROM cameras WHERE owner_id = $2)
        WHERE p.id = $1 AND p.owner_id = $2
        GROUP BY p.id
        """,
        person_id,
        user["sub"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="person not found")
    return _person_out(row)


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
    # Keep historical evidence while removing the identity association. The
    # foreign keys are intentionally restrictive, so clear references before
    # deleting the person and hold its row lock for the whole operation.
    async with db.transaction():
        exists = await db.fetchval(
            "SELECT 1 FROM persons WHERE id = $1 AND owner_id = $2 FOR UPDATE",
            person_id,
            user["sub"],
        )
        if not exists:
            raise HTTPException(status_code=404, detail="person not found")
        await db.execute(
            "UPDATE detections SET person_id = NULL, "
            "association_confidence = NULL, association_method = NULL "
            "WHERE person_id = $1",
            person_id,
        )
        await db.execute(
            "UPDATE events SET person_id = NULL WHERE person_id = $1",
            person_id,
        )
        await db.execute("DELETE FROM persons WHERE id = $1", person_id)
