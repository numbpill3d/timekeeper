"""Alert rule CRUD + delivery history."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from ..auth import CurrentUser
from ..db import get_db

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]

_ALLOWED = {"is_active", "name", "rule_text", "priority", "channels", "compiled_rule"}


class AlertRuleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    rule_text: str = Field(min_length=1, max_length=1000)
    priority: Literal["critical", "important", "informational"] = "important"
    channels: list[Literal["push", "sms"]] = Field(default_factory=lambda: ["push"], min_length=1, max_length=2)

    @field_validator("name", "rule_text")
    @classmethod
    def _strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("value cannot be empty")
        return value


class AlertRuleUpdate(BaseModel):
    is_active: bool | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    rule_text: str | None = Field(default=None, min_length=1, max_length=1000)
    priority: Literal["critical", "important", "informational"] | None = None
    channels: list[Literal["push", "sms"]] | None = Field(default=None, min_length=1, max_length=2)

    @field_validator("name", "rule_text")
    @classmethod
    def _strip_optional_text(cls, value: str | None) -> str | None:
        value = value.strip() if value is not None else None
        if value == "":
            raise ValueError("value cannot be empty")
        return value


class AlertRuleOut(BaseModel):
    id: UUID
    name: str
    rule_text: str
    priority: str
    channels: list[str]
    is_active: bool
    created_at: datetime


class AlertDeliveryOut(BaseModel):
    id: UUID
    rule_id: UUID
    event_id: UUID
    triggered_at: datetime
    channels_sent: list[str]


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


@router.patch("/{rule_id}", response_model=AlertRuleOut)
async def update_rule(
    rule_id: UUID, req: AlertRuleUpdate, user: CurrentUser, db: DB
) -> AlertRuleOut:
    updates = {
        k: v
        for k, v in req.model_dump(exclude_none=True).items()
        if k in _ALLOWED
    }
    if not updates:
        raise HTTPException(status_code=422, detail="no fields to update")
    if "rule_text" in updates:
        # The compiled predicate is derived from rule_text and must never
        # survive a text edit, otherwise the UI appears to save a new rule
        # while the worker continues evaluating the previous one.
        updates["compiled_rule"] = None
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
        "SELECT * FROM alert_rules WHERE id = $1 AND owner_id = $2",
        rule_id,
        user["sub"],
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


@router.get("/{rule_id}/deliveries", response_model=list[AlertDeliveryOut])
async def list_deliveries(
    rule_id: UUID,
    user: CurrentUser,
    db: DB,
    limit: int = Query(50, ge=1, le=200),
) -> list[AlertDeliveryOut]:
    exists = await db.fetchval(
        "SELECT 1 FROM alert_rules WHERE id = $1 AND owner_id = $2",
        rule_id,
        user["sub"],
    )
    if not exists:
        raise HTTPException(status_code=404, detail="rule not found")
    rows = await db.fetch(
        """
        SELECT * FROM alert_deliveries
        WHERE rule_id = $1
        ORDER BY triggered_at DESC
        LIMIT $2
        """,
        rule_id,
        limit,
    )
    return [AlertDeliveryOut(**dict(r)) for r in rows]
