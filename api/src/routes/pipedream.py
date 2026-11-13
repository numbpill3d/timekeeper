"""Pipedream Connect managed-auth endpoints."""

from __future__ import annotations

import os
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..auth import CurrentUser

router = APIRouter(prefix="/integrations/pipedream")

_API_URL = "https://api.pipedream.com/v1"
_PROJECT_ID = os.getenv("PIPEDREAM_PROJECT_ID", "").strip()
_ENVIRONMENT = os.getenv("PIPEDREAM_ENVIRONMENT", "production").strip()


class ConnectTokenResponse(BaseModel):
    token: str
    connect_link_url: str
    expires_at: str | None = None


def _configured() -> tuple[str, str]:
    if not _PROJECT_ID:
        raise HTTPException(
            status_code=503,
            detail="Pipedream project is not configured on this deployment",
        )
    client_id = os.getenv("PIPEDREAM_CLIENT_ID", "").strip()
    client_secret = os.getenv("PIPEDREAM_CLIENT_SECRET", "").strip()
    if _ENVIRONMENT not in {"development", "production"}:
        raise HTTPException(
            status_code=503,
            detail="Pipedream environment is invalid on this deployment",
        )
    if not client_id or not client_secret:
        raise HTTPException(
            status_code=503,
            detail="Pipedream Connect is not configured on this deployment",
        )
    return client_id, client_secret


def _validate_connect_link(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    parsed = urlparse(candidate)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        return None
    return candidate


@router.post("/connect-token", response_model=ConnectTokenResponse)
async def create_connect_token(user: CurrentUser) -> ConnectTokenResponse:
    """Mint a short-lived Connect Link token for the authenticated user."""
    client_id, client_secret = _configured()
    payload: dict[str, str] = {
        "external_user_id": str(user["sub"]),
    }
    redirect_uri = os.getenv("PIPEDREAM_SUCCESS_REDIRECT_URI", "").strip()
    if redirect_uri:
        payload["success_redirect_uri"] = redirect_uri

    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=False) as client:
            oauth = await client.post(
                f"{_API_URL}/oauth/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            oauth.raise_for_status()
            oauth_data = oauth.json()
            if not isinstance(oauth_data, dict):
                raise TypeError("Pipedream OAuth response was not an object")
            access_token = oauth_data.get("access_token")
            if not isinstance(access_token, str) or not access_token.strip():
                raise ValueError("Pipedream OAuth response did not include an access token")

            response = await client.post(
                f"{_API_URL}/connect/{_PROJECT_ID}/tokens",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "x-pd-project-id": _PROJECT_ID,
                    "x-pd-environment": _ENVIRONMENT,
                },
                json=payload,
            )
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=502,
            detail="Pipedream Connect token creation failed",
        ) from exc

    if not isinstance(data, dict):
        raise HTTPException(
            status_code=502,
            detail="Pipedream returned an invalid Connect token response",
        )
    token = data.get("token")
    connect_link_url = _validate_connect_link(
        data.get("connect_link_url") or data.get("connectLinkUrl")
    )
    if not isinstance(token, str) or not token.strip():
        token = None
    if not isinstance(connect_link_url, str) or not connect_link_url.strip():
        connect_link_url = None
    if not token or not connect_link_url:
        raise HTTPException(
            status_code=502,
            detail="Pipedream returned an incomplete or unsafe Connect token response",
        )
    return ConnectTokenResponse(
        token=token,
        connect_link_url=connect_link_url,
        expires_at=data.get("expires_at") or data.get("expiresAt"),
    )
