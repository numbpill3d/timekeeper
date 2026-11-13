"""Static checks for migration ledger consistency."""

import re
from pathlib import Path

MIGRATION_DIR = Path(__file__).parents[1] / "infra" / "db" / "migrations"
COMPOSE_FILE = Path(__file__).parents[1] / "docker-compose.yml"


def test_every_numbered_migration_records_its_version():
    migrations = sorted(MIGRATION_DIR.glob("[0-9][0-9][0-9]_*.sql"))

    assert migrations
    for migration in migrations:
        version = migration.stem
        contents = migration.read_text(encoding="utf-8")
        assert re.search(
            rf"VALUES\s*\(\s*'{re.escape(version)}'\s*\)",
            contents,
            re.IGNORECASE,
        ), f"{migration.name} does not record {version}"


def test_compose_migration_runner_uses_the_ledger():
    """The migration sidecar must not re-run completed upgrades forever."""
    contents = COMPOSE_FILE.read_text(encoding="utf-8")
    assert "schema_migrations" in contents
    assert "SELECT 1 FROM schema_migrations" in contents
    assert "skipping applied migration" in contents


def test_fresh_and_upgraded_embedding_indexes_use_one_canonical_name():
    init = (MIGRATION_DIR.parent / "init.sql").read_text(encoding="utf-8")
    migration = (MIGRATION_DIR / "001_provider_attribution.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE INDEX events_embedding_384_idx" in init
    assert "DROP INDEX IF EXISTS events_embedding_idx" in migration
    assert "CREATE INDEX IF NOT EXISTS events_embedding_384_idx" in migration


def test_camera_health_migration_records_status_columns():
    migration = (MIGRATION_DIR / "006_camera_health.sql").read_text(encoding="utf-8")
    assert "last_frame_at" in migration
    assert "last_error_code" in migration
    assert "VALUES ('006_camera_health')" in migration


def test_camera_frame_metrics_migration_records_diagnostic_columns():
    migration = (MIGRATION_DIR / "007_camera_frame_metrics.sql").read_text(encoding="utf-8")
    assert "last_frame_width" in migration
    assert "last_frame_height" in migration
    assert "observed_fps" in migration
    assert "VALUES ('007_camera_frame_metrics')" in migration


def test_event_annotation_migration_keeps_notes_owner_scoped_and_bounded():
    migration = (MIGRATION_DIR / "009_event_annotations.sql").read_text(encoding="utf-8")
    assert "owner_id" in migration
    assert "char_length(note) BETWEEN 1 AND 2000" in migration
    assert "PRIMARY KEY (event_id, owner_id)" in migration
    assert "VALUES ('009_event_annotations')" in migration
