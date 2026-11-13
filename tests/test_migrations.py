"""Static checks for migration ledger consistency."""

import re
from pathlib import Path

MIGRATION_DIR = Path(__file__).parents[1] / "infra" / "db" / "migrations"


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
