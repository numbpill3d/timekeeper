"""
JWT auth + password hashing.

Zero-trust model: every request carries a short-lived JWT.
Refresh tokens are stored in Redis with rotation on each use.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

_SECRET = os.getenv("JWT_SECRET", "change-me")
_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
_EXPIRE_MIN = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer()


# ── Password utils ────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


# ── Token utils ───────────────────────────────────────────────────

def create_access_token(user_id: str, tier: str) -> str:
    expire = datetime.now(tz=timezone.utc) + timedelta(minutes=_EXPIRE_MIN)
    return jwt.encode(
        {"sub": user_id, "tier": tier, "exp": expire},
        _SECRET,
        algorithm=_ALGORITHM,
    )


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, _SECRET, algorithms=[_ALGORITHM])
    except JWTError as exc:
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
