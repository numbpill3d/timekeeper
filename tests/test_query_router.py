"""Safety and ownership tests for generated surveillance queries."""

import pytest

from router import _inject_owner_scope, _safe_sql


def test_safe_sql_requires_events_and_rejects_multiple_statements():
    assert _safe_sql("SELECT e.id FROM events e")
    with pytest.raises(ValueError):
        _safe_sql("SELECT 1")
    with pytest.raises(ValueError):
        _safe_sql("SELECT e.id FROM events e; DELETE FROM events")


def test_owner_scope_respects_an_alias():
    sql = _inject_owner_scope("SELECT e.id FROM events AS e WHERE e.event_type = 'object_moved'")
    assert "e.camera_id IN" in sql
    assert "$1::uuid" in sql


def test_owner_scope_without_alias_does_not_use_sql_keyword_as_alias():
    sql = _inject_owner_scope("SELECT events.id FROM events WHERE events.event_type = 'person_entered'")
    assert "events.camera_id IN" in sql
