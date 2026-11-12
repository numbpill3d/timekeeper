"""Unit tests for alert rule compilation and event matching."""

from datetime import datetime, timezone
from uuid import uuid4

from omniscient_shared.models.event import Event, EventType
from rules import compile_rule, event_matches, normalize_rule


def _event(
    event_type: EventType = EventType.person_entered,
    location_label: str | None = None,
    confidence: float = 1.0,
    hour: int = 12,
) -> Event:
    return Event(
        camera_id=uuid4(),
        event_type=event_type,
        timestamp=datetime(2024, 1, 15, hour, 0, tzinfo=timezone.utc),
        action_label="test event",
        location_label=location_label,
        confidence=confidence,
    )


# ── compile_rule ──────────────────────────────────────────────────

def test_compile_unknown_person_template():
    result = compile_rule("alert when unknown person enters")
    assert EventType.person_entered.value in result.get("event_types", [])


def test_compile_package_template():
    result = compile_rule("notify on package delivered")
    assert EventType.package_delivered.value in result.get("event_types", [])


def test_compile_no_match_returns_empty():
    result = compile_rule("some completely unrecognized rule xyz123")
    assert result == {}


def test_invalid_compiled_rule_is_rejected():
    assert normalize_rule({"event_types": ["read_users_table"]}) == {}
    assert normalize_rule({"time_after": "25:99"}) == {}
    assert normalize_rule({"min_confidence": 2}) == {}


def test_disabled_rule_never_matches():
    assert event_matches(_event(), {"_disabled": True}, person_label=None) is False


# ── event type filter ─────────────────────────────────────────────

def test_empty_rule_matches_all():
    assert event_matches(_event(), {}, person_label=None) is True


def test_event_type_matches():
    rule = {"event_types": [EventType.person_entered.value]}
    result = event_matches(_event(EventType.person_entered), rule, person_label="alice")
    assert result is True


def test_event_type_does_not_match():
    rule = {"event_types": [EventType.intrusion_detected.value]}
    result = event_matches(_event(EventType.person_entered), rule, person_label=None)
    assert result is False


# ── person label filter ───────────────────────────────────────────

def test_unknown_triggers_for_unidentified_person():
    rule = {"person_labels": ["unknown"]}
    result = event_matches(
        _event(), rule, person_label="Unknown A3F", person_is_known=False
    )
    assert result is True


def test_unknown_skips_identified_person():
    rule = {"person_labels": ["unknown"]}
    result = event_matches(_event(), rule, person_label="alice", person_is_known=True)
    assert result is False


def test_specific_label_matches():
    rule = {"person_labels": ["alice"]}
    assert event_matches(_event(), rule, person_label="alice") is True


def test_specific_label_rejects_wrong_name():
    rule = {"person_labels": ["alice"]}
    assert event_matches(_event(), rule, person_label="bob") is False


# ── object category filter ────────────────────────────────────────

def test_object_category_matches():
    rule = {"object_categories": ["keys"]}
    result = event_matches(_event(), rule, person_label=None, object_category="keys")
    assert result is True


def test_object_category_rejects_other():
    rule = {"object_categories": ["keys"]}
    result = event_matches(
        _event(), rule, person_label=None, object_category="phone"
    )
    assert result is False


# ── location filter ───────────────────────────────────────────────

def test_location_matches():
    rule = {"location_labels": ["front door"]}
    result = event_matches(
        _event(location_label="front door"), rule, person_label=None
    )
    assert result is True


def test_location_rejects_other():
    rule = {"location_labels": ["front door"]}
    result = event_matches(
        _event(location_label="backyard"), rule, person_label=None
    )
    assert result is False


# ── time window filter ────────────────────────────────────────────

def test_time_after_within_window():
    result = event_matches(_event(hour=10), {"time_after": "06:00"}, person_label=None)
    assert result is True


def test_time_after_too_early():
    result = event_matches(_event(hour=4), {"time_after": "06:00"}, person_label=None)
    assert result is False


def test_time_before_within_window():
    result = event_matches(
        _event(hour=20), {"time_before": "22:00"}, person_label=None
    )
    assert result is True


def test_time_before_too_late():
    result = event_matches(
        _event(hour=23), {"time_before": "22:00"}, person_label=None
    )
    assert result is False


def test_time_window_inside():
    rule = {"time_after": "00:00", "time_before": "06:00"}
    assert event_matches(_event(hour=2), rule, person_label=None) is True


def test_time_window_outside():
    rule = {"time_after": "00:00", "time_before": "06:00"}
    assert event_matches(_event(hour=10), rule, person_label=None) is False


# ── confidence filter ─────────────────────────────────────────────

def test_min_confidence_passes():
    result = event_matches(
        _event(confidence=0.9), {"min_confidence": 0.7}, person_label=None
    )
    assert result is True


def test_min_confidence_rejects_low():
    result = event_matches(
        _event(confidence=0.5), {"min_confidence": 0.7}, person_label=None
    )
    assert result is False
