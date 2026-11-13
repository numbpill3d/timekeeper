"""Regression checks for Compose wiring that is not covered by YAML parsing."""

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]


def test_provider_secret_directory_is_mounted_for_consumers():
    compose = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    mount = "${TIMEKEEPER_SECRETS_DIR:-./secrets}:/run/secrets:ro"
    assert compose.count(mount) == 2
    assert "RING_ACCESS_TOKEN_FILE: ${RING_ACCESS_TOKEN_FILE}" in compose
    assert "FCM_SERVICE_ACCOUNT_FILE: ${FCM_SERVICE_ACCOUNT_FILE}" in compose


def test_application_services_do_not_inherit_the_full_env_file():
    compose = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "env_file:" not in compose
    for name in (
        "TIMEZONE",
        "FRAME_STORE_PATH",
        "CAMERA_REFRESH_INTERVAL_S",
        "PIPEDREAM_CLIENT_SECRET",
    ):
        assert f"{name}: ${{{name}}}" in compose


def test_ingestion_declares_all_provider_credential_inputs():
    compose = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    ingestion = compose.split("  ingestion:\n", 1)[1].split("  vision:\n", 1)[0]
    for provider in ("RING", "NEST", "ARLO", "WYZE"):
        for suffix in (
            "ACCESS_TOKEN",
            "ACCESS_TOKEN_FILE",
            "REFRESH_TOKEN",
            "REFRESH_TOKEN_FILE",
            "TOKEN_URL",
            "CLIENT_ID",
            "CLIENT_SECRET",
        ):
            name = f"{provider}_{suffix}"
            assert f"{name}: ${{{name}}}" in ingestion
