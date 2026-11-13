from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from scripts.seed_synthetic import _base_time, _id, _story_events


def test_fixture_ids_are_stable_and_isolated_by_owner_and_name():
    owner = UUID("00000000-0000-0000-0000-000000000001")
    assert _id(owner, "toolbox-demo", "camera") == _id(owner, "toolbox-demo", "camera")
    assert _id(owner, "toolbox-demo", "camera") != _id(owner, "other", "camera")
    assert _id(owner, "toolbox-demo", "camera") != _id(UUID(int=2), "toolbox-demo", "camera")


def test_fixture_time_defaults_to_utc_and_accepts_z_suffix():
    parsed = _base_time("2026-11-13T16:30:00Z")
    assert parsed == datetime(2026, 11, 13, 16, 30, tzinfo=UTC)
    assert _base_time("2026-11-13T16:30:00").tzinfo is UTC


def test_demo_sequence_uses_a_stable_five_step_story():
    source = Path("scripts/seed_synthetic.py").read_text(encoding="utf-8")
    assert '"object_picked_up"' in source
    assert '"object_moved"' in source
    assert '"object_placed"' in source
    assert '"person_exited"' in source


def test_demo_story_uses_two_cameras_and_preserves_handoff_path():
    kitchen_camera = UUID(int=10)
    garage_camera = UUID(int=11)
    events = _story_events(
        datetime(2026, 11, 13, 16, 30, tzinfo=UTC),
        kitchen_camera,
        garage_camera,
        UUID(int=12),
        UUID(int=13),
        "toolbox-demo",
    )

    assert [event["event_type"] for event in events] == [
        "person_entered",
        "object_picked_up",
        "object_moved",
        "object_placed",
        "person_exited",
    ]
    assert events[1]["camera_id"] == kitchen_camera
    assert events[2]["camera_id"] == garage_camera
    assert events[2]["metadata"]["from_camera_name"].endswith("· kitchen")
    assert events[2]["metadata"]["to_camera_name"].endswith("· garage")


def test_fixture_supports_email_owner_lookup_without_account_creation():
    source = Path("scripts/seed_synthetic.py").read_text(encoding="utf-8")
    assert "lower(email) = lower($1)" in source
    assert "INSERT INTO users" not in source
