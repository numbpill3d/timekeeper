"""Regression tests for auth/profile API contracts."""

from datetime import UTC, datetime

import pytest

from api.src.routes.users import (
    LoginRequest,
    ProfileUpdate,
    RegisterRequest,
    update_profile,
)


def test_auth_email_is_canonicalized_case_insensitively():
    assert RegisterRequest(
        email="Alice.Example@Example.COM", password="correct horse battery staple"
    ).email == "alice.example@example.com"
    assert LoginRequest(
        email="ALICE.EXAMPLE@EXAMPLE.COM", password="correct horse battery staple"
    ).email == "alice.example@example.com"


class _ProfileDb:
    def __init__(self) -> None:
        self.updates: tuple[object, ...] | None = None

    async def execute(self, _sql: str, *params: object) -> None:
        self.updates = params

    async def fetchrow(self, _sql: str, _user_id: str) -> dict:
        return {
            "email": "alice.example@example.com",
            "subscription_tier": "home",
            "fcm_token": "token-2",
            "phone": "+15551234567",
            "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        }


@pytest.mark.asyncio
async def test_profile_update_returns_the_full_profile_contract():
    db = _ProfileDb()
    result = await update_profile(
        ProfileUpdate(fcm_token="token-2"),
        {"sub": "00000000-0000-0000-0000-000000000001"},
        db,
    )
    assert db.updates == (
        "00000000-0000-0000-0000-000000000001",
        "token-2",
    )
    assert result["email"] == "alice.example@example.com"
    assert result["tier"] == "home"
    assert result["fcm_token"] == "token-2"
