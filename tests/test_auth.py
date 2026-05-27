"""Unit tests for JWT auth and password hashing."""

import os

import pytest

# Must be set before auth module is imported (evaluated at module level)
os.environ["JWT_SECRET"] = "test-secret-for-unit-tests-only-must-be-32c"

from fastapi import HTTPException  # noqa: E402
from auth import (  # noqa: E402
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


# ── password hashing ──────────────────────────────────────────────

def test_hash_is_not_plaintext():
    hashed = hash_password("correcthorsebatterystaple")
    assert hashed != "correcthorsebatterystaple"


def test_correct_password_verifies():
    plain = "correcthorsebatterystaple"
    assert verify_password(plain, hash_password(plain)) is True


def test_wrong_password_fails():
    assert verify_password("wrongpassword", hash_password("rightpassword")) is False


# ── JWT token ─────────────────────────────────────────────────────

def test_token_roundtrip():
    token = create_access_token("user-abc", "home")
    payload = decode_token(token)
    assert payload["sub"] == "user-abc"
    assert payload["tier"] == "home"


def test_different_user_ids_produce_different_tokens():
    t1 = create_access_token("user-1", "free")
    t2 = create_access_token("user-2", "free")
    assert t1 != t2


def test_invalid_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        decode_token("not.a.valid.jwt.token")
    assert exc_info.value.status_code == 401


def test_tampered_signature_raises_401():
    token = create_access_token("user-xyz", "pro")
    last = token[-1]
    tampered = token[:-1] + ("A" if last != "A" else "B")
    with pytest.raises(HTTPException) as exc_info:
        decode_token(tampered)
    assert exc_info.value.status_code == 401


def test_tier_preserved_in_token():
    for tier in ("free", "home", "family", "pro"):
        payload = decode_token(create_access_token("u", tier))
        assert payload["tier"] == tier
