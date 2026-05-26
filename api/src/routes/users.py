"""Auth routes: register, login, profile."""

from __future__ import annotations

from typing import Annotated

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from ..auth import (
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)
from ..db import get_db

router = APIRouter()

DB = Annotated[asyncpg.Connection, Depends(get_db)]


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


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

    row = await db.fetchrow(
        """
        INSERT INTO users (email, password_hash)
        VALUES ($1, $2)
        RETURNING id, subscription_tier
        """,
        req.email,
        hash_password(req.password),
    )
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
    fcm_token: str | None = None
    phone: str | None = None


@router.patch("/me")
async def update_profile(
    req: ProfileUpdate, user: CurrentUser, db: DB
) -> dict:
    updates: dict = {}
    if req.fcm_token is not None:
        updates["fcm_token"] = req.fcm_token
    if req.phone is not None:
        updates["phone"] = req.phone
    if not updates:
        return {"user_id": user["sub"]}
    sets = ", ".join(
        f"{col} = ${i + 2}" for i, col in enumerate(updates)
    )
    await db.execute(
        f"UPDATE users SET {sets} WHERE id = $1",
        user["sub"],
        *updates.values(),
    )
    return {"user_id": user["sub"], **updates}
