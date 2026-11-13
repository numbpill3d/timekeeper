"""Unit tests for alert rule compilation and event matching."""

import asyncio
import sys
import types
from datetime import UTC, datetime
from uuid import uuid4

import pytest
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
        timestamp=datetime(2024, 1, 15, hour, 0, tzinfo=UTC),
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


@pytest.mark.parametrize(
    ("text", "event_type"),
    [
        ("alert when a person detected", EventType.person_detected),
        ("alert when the door opened", EventType.door_opened),
        ("alert when the door closed", EventType.door_closed),
        ("alert when a fall detected", EventType.fall_detected),
    ],
)
def test_compile_new_event_templates(text, event_type):
    assert compile_rule(text) == {"event_types": [event_type.value]}


def test_compile_no_match_returns_empty():
    result = compile_rule("some completely unrecognized rule xyz123")
    assert result == {}


def test_fenced_rule_json_removes_only_the_language_marker(monkeypatch):
    import rules

    class FakeClient:
        async def chat(self, **_kwargs):
            return {
                "message": {
                    "content": '```json\n{"event_types": ["person_entered"]}\n```'
                }
            }

    monkeypatch.setitem(
        sys.modules,
        "ollama",
        types.SimpleNamespace(AsyncClient=lambda **_kwargs: FakeClient()),
    )
    result = asyncio.run(rules.compile_rule_llm("someone enters"))
    assert result == {"event_types": ["person_entered"]}


def test_rule_compilation_times_out_without_blocking_alerts(monkeypatch):
    import rules

    class SlowClient:
        async def chat(self, **_kwargs):
            await asyncio.sleep(1)

    monkeypatch.setitem(
        sys.modules,
        "ollama",
        types.SimpleNamespace(AsyncClient=lambda **_kwargs: SlowClient()),
    )
    monkeypatch.setattr(rules, "_OLLAMA_TIMEOUT_SECONDS", 0.01)

    assert asyncio.run(rules.compile_rule_llm("someone enters")) == {}


def test_invalid_compiled_rule_is_rejected():
    assert normalize_rule({"event_types": ["read_users_table"]}) == {}
    assert normalize_rule({"time_after": "25:99"}) == {}
    assert normalize_rule({"min_confidence": 2}) == {}


def test_disabled_rule_never_matches():
    assert event_matches(_event(), {"_disabled": True}, person_label=None) is False


def test_disabled_rule_marker_survives_normalization():
    disabled = normalize_rule({"_disabled": True})
    assert disabled == {"_disabled": True}
    assert event_matches(_event(), disabled, person_label=None) is False


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


def test_unknown_does_not_match_events_without_a_person_association():
    rule = {"person_labels": ["unknown"]}
    assert event_matches(_event(), rule, person_label=None, person_is_known=False) is False


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


def test_labels_and_locations_match_case_insensitively():
    rule = {
        "person_labels": ["john"],
        "object_categories": ["keys"],
        "location_labels": ["front door"],
    }
    event = _event(location_label="Front Door")
    assert event_matches(
        event,
        rule,
        person_label="John",
        object_category="Keys",
    ) is True


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


def test_time_window_crossing_midnight():
    rule = {"time_after": "22:00", "time_before": "06:00"}
    assert event_matches(_event(hour=23), rule, person_label=None) is True
    assert event_matches(_event(hour=2), rule, person_label=None) is True
    assert event_matches(_event(hour=12), rule, person_label=None) is False


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
