"""Auth routes: register, login, profile."""

from __future__ import annotations

import re
from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field, field_validator

from ..auth import (
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)
from ..db import get_db

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]


def _normalize_email(value: EmailStr) -> str:
    """Use one case-insensitive identity for registration and login."""
    return str(value).strip().casefold()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _canonical_email(cls, value: EmailStr) -> str:
        return _normalize_email(value)

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("password must be at least 8 characters")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _canonical_email(cls, value: EmailStr) -> str:
        return _normalize_email(value)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(req: RegisterRequest, db: DB) -> TokenResponse:
    existing = await db.fetchrow(
        "SELECT id FROM users WHERE email = $1", req.email
    )
    if existing:
        raise HTTPException(status_code=409, detail="email already registered")

    try:
        row = await db.fetchrow(
            """
            INSERT INTO users (email, password_hash)
            VALUES ($1, $2)
            RETURNING id, subscription_tier
            """,
            req.email,
            hash_password(req.password),
        )
    except asyncpg.UniqueViolationError as exc:
        # The pre-check is only a friendly fast path; the unique index is the
        # authority when two registrations race.
        raise HTTPException(status_code=409, detail="email already registered") from exc
    token = create_access_token(str(row["id"]), row["subscription_tier"])
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, db: DB) -> TokenResponse:
    row = await db.fetchrow(
        "SELECT id, password_hash, subscription_tier FROM users WHERE email=$1",
        req.email,
    )
    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid credentials",
        )
    token = create_access_token(str(row["id"]), row["subscription_tier"])
    return TokenResponse(access_token=token)


@router.get("/me")
async def me(user: CurrentUser, db: DB) -> dict:
    row = await db.fetchrow(
        "SELECT email, subscription_tier, fcm_token, phone, created_at "
        "FROM users WHERE id = $1",
        user["sub"],
    )
    if not row:
        raise HTTPException(status_code=404, detail="user not found")
    return {
        "user_id": user["sub"],
        "tier": row["subscription_tier"],
        "email": row["email"],
        "fcm_token": row["fcm_token"],
        "phone": row["phone"],
        "created_at": row["created_at"].isoformat() if row["created_at"] else None,
    }


class ProfileUpdate(BaseModel):
    fcm_token: str | None = Field(default=None, max_length=4096)
    phone: str | None = Field(default=None, max_length=16)

    @field_validator("fcm_token")
    @classmethod
    def _trim_fcm_token(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("fcm_token cannot be empty")
        return value

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not re.fullmatch(r"\+[1-9]\d{7,14}", value):
            raise ValueError("phone must be an E.164 number")
        return value


@router.patch("/me")
async def update_profile(
    req: ProfileUpdate, user: CurrentUser, db: DB
) -> dict:
    _ALLOWED = {"fcm_token", "phone"}
    updates: dict = {}
    # `model_fields_set` distinguishes an omitted field (leave it unchanged)
    # from an explicit null (clear the stored notification destination).
    if "fcm_token" in req.model_fields_set:
        updates["fcm_token"] = req.fcm_token
    if "phone" in req.model_fields_set:
        updates["phone"] = req.phone
    if not updates:
        return await me(user, db)
    assert set(updates) <= _ALLOWED
    sets = ", ".join(
        f"{col} = ${i + 2}" for i, col in enumerate(updates)
    )
    await db.execute(
        f"UPDATE users SET {sets} WHERE id = $1",
        user["sub"],
        *updates.values(),
    )
    return await me(user, db)
