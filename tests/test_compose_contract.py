"""Regression checks for Compose wiring that is not covered by YAML parsing."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_provider_secret_directory_is_mounted_for_consumers():
    compose = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    mount = "${TIMEKEEPER_SECRETS_DIR:-./secrets}:/run/secrets:ro"
    assert compose.count(mount) == 2
    assert "RING_ACCESS_TOKEN_FILE: ${RING_ACCESS_TOKEN_FILE}" in compose
    assert "FCM_SERVICE_ACCOUNT_FILE: ${FCM_SERVICE_ACCOUNT_FILE}" in compose
