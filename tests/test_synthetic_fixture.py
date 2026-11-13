from datetime import UTC, datetime
from uuid import UUID

from scripts.seed_synthetic import _base_time, _id


def test_fixture_ids_are_stable_and_isolated_by_owner_and_name():
    owner = UUID("00000000-0000-0000-0000-000000000001")
    assert _id(owner, "toolbox-demo", "camera") == _id(owner, "toolbox-demo", "camera")
    assert _id(owner, "toolbox-demo", "camera") != _id(owner, "other", "camera")
    assert _id(owner, "toolbox-demo", "camera") != _id(UUID(int=2), "toolbox-demo", "camera")


def test_fixture_time_defaults_to_utc_and_accepts_z_suffix():
    parsed = _base_time("2026-11-13T16:30:00Z")
    assert parsed == datetime(2026, 11, 13, 16, 30, tzinfo=UTC)
    assert _base_time("2026-11-13T16:30:00").tzinfo is UTC
