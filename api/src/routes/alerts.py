"""Alert rule CRUD."""

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


class AlertRuleCreate(BaseModel):
    name: str
    rule_text: str
    priority: str = "important"
    channels: list[str] = ["push"]


class AlertRuleUpdate(BaseModel):
    is_active: bool | None = None
    name: str | None = None
    rule_text: str | None = None
    priority: str | None = None
    channels: list[str] | None = None


class AlertRuleOut(BaseModel):
    id: UUID
    name: str
    rule_text: str
    priority: str
    channels: list[str]
    is_active: bool
    created_at: datetime


@router.patch("/{rule_id}", response_model=AlertRuleOut)
async def update_rule(
    rule_id: UUID, req: AlertRuleUpdate, user: CurrentUser, db: DB
) -> AlertRuleOut:
    updates: dict = {
        k: v
        for k, v in req.model_dump(exclude_none=True).items()
    }
    if not updates:
        raise HTTPException(status_code=422, detail="no fields to update")
    sets = ", ".join(f"{col} = ${i + 3}" for i, col in enumerate(updates))
    result = await db.execute(
        f"UPDATE alert_rules SET {sets} WHERE id = $1 AND owner_id = $2",
        rule_id,
        user["sub"],
        *updates.values(),
    )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="rule not found")
    row = await db.fetchrow(
        "SELECT * FROM alert_rules WHERE id = $1", rule_id
    )
    return AlertRuleOut(**dict(row))


@router.get("", response_model=list[AlertRuleOut])
async def list_rules(user: CurrentUser, db: DB) -> list[AlertRuleOut]:
    rows = await db.fetch(
        "SELECT * FROM alert_rules WHERE owner_id = $1 ORDER BY created_at",
        user["sub"],
    )
    return [AlertRuleOut(**dict(r)) for r in rows]


@router.post("", response_model=AlertRuleOut, status_code=201)
async def create_rule(
    req: AlertRuleCreate, user: CurrentUser, db: DB
) -> AlertRuleOut:
    row = await db.fetchrow(
        """
        INSERT INTO alert_rules (owner_id, name, rule_text, priority, channels)
        VALUES ($1, $2, $3, $4, $5)
        RETURNING *
        """,
        user["sub"],
        req.name,
        req.rule_text,
        req.priority,
        req.channels,
    )
    return AlertRuleOut(**dict(row))


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: UUID, user: CurrentUser, db: DB) -> None:
    result = await db.execute(
        "DELETE FROM alert_rules WHERE id = $1 AND owner_id = $2",
        rule_id,
        user["sub"],
    )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="rule not found")
