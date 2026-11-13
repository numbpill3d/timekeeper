"""
JWT auth + password hashing.

Zero-trust model: every request carries a short-lived JWT.
"""

from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

import bcrypt as _bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

_SECRET = os.getenv("JWT_SECRET")
if not _SECRET:
    raise RuntimeError(
        "JWT_SECRET environment variable is not set. "
        "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
    )
if len(_SECRET) < 32:
    raise RuntimeError("JWT_SECRET must contain at least 32 characters")
if os.getenv("ENVIRONMENT", "development").lower() == "production" and _SECRET in {
    "changeme",
    "secret",
    "test-secret-for-unit-tests-only-must-be-32c",
    "local-development-secret-change-me-please-123456",
}:
    raise RuntimeError("JWT_SECRET must be unique in production")
_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256").upper()
if _ALGORITHM not in {"HS256", "HS384", "HS512"}:
    raise RuntimeError("JWT_ALGORITHM must be HS256, HS384, or HS512")
try:
    _EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))
except ValueError as exc:
    raise RuntimeError("JWT_EXPIRE_MINUTES must be an integer") from exc
if not 1 <= _EXPIRE_MIN <= 1440:
    raise RuntimeError("JWT_EXPIRE_MINUTES must be between 1 and 1440")

_bearer = HTTPBearer()
_VALID_TIERS = {"free", "home", "family", "pro"}


# ── Password utils ────────────────────────────────────────────────

def _prepare(plain: str) -> bytes:
    # SHA-256 pre-hash keeps input well under bcrypt's 72-byte limit.
    return hashlib.sha256(plain.encode()).digest()


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(_prepare(plain), _bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(_prepare(plain), hashed.encode())
    except (TypeError, ValueError):
        # A corrupt legacy row must behave like any other invalid credential,
        # not turn the login endpoint into a 500 response.
        return False


# ── Token utils ───────────────────────────────────────────────────

def create_access_token(user_id: str, tier: str) -> str:
    try:
        UUID(user_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("user_id must be a UUID") from exc
    if tier not in _VALID_TIERS:
        raise ValueError("tier is invalid")
    expire = datetime.now(tz=UTC) + timedelta(minutes=_EXPIRE_MIN)
    return jwt.encode(
        {"sub": user_id, "tier": tier, "exp": expire},
        _SECRET,
        algorithm=_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
        if not isinstance(payload.get("sub"), str):
            raise TypeError("token subject is missing")
        UUID(payload["sub"])
        if payload.get("tier") not in _VALID_TIERS:
            raise ValueError("token tier is invalid")
        return payload
    except (JWTError, TypeError, ValueError, AttributeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired token",
        ) from exc


# ── FastAPI dependency ────────────────────────────────────────────

def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(_bearer)],
) -> dict:
    """Dependency that validates the bearer token and returns the payload."""
    return decode_token(creds.credentials)


CurrentUser = Annotated[dict, Depends(get_current_user)]


def require_tier(*tiers: str):
    """Dependency factory: raises 403 if user's tier isn't in tiers."""
    def _check(user: CurrentUser) -> dict:
        if user.get("tier") not in tiers:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"requires one of: {tiers}",
            )
        return user
    return Depends(_check)
