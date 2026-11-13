"""Static contracts for bounded service retry boundaries."""

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_database_timeout_is_retriable_in_long_running_workers():
    sources = (
        ROOT / "services/ingestion/src/main.py",
        ROOT / "services/event-processor/src/main.py",
        ROOT / "services/vision/src/pipeline.py",
    )
    for source in sources:
        text = source.read_text(encoding="utf-8")
        assert "timeout=_DB_CONNECT_TIMEOUT_SECONDS" in text
        assert "asyncpg.PostgresError, TimeoutError" in text
