"""Safety and ownership tests for generated surveillance queries."""

import pytest

from router import _inject_owner_scope, _safe_sql


def test_safe_sql_requires_events_and_rejects_multiple_statements():
    assert _safe_sql("SELECT e.id FROM events e")
    with pytest.raises(ValueError):
        _safe_sql("SELECT 1")
    with pytest.raises(ValueError):
        _safe_sql("SELECT e.id FROM events e; DELETE FROM events")


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT id FROM events WHERE id IN (SELECT id FROM users)",
        "SELECT id FROM events UNION SELECT id FROM users",
        "WITH leaked AS (SELECT * FROM users) SELECT id FROM events",
    ],
)
def test_safe_sql_rejects_unscoped_or_composed_queries(sql):
    with pytest.raises(ValueError):
        _safe_sql(sql)


def test_owner_scope_respects_an_alias():
    sql = _inject_owner_scope("SELECT e.id FROM events AS e WHERE e.event_type = 'object_moved'")
    assert "e.camera_id IN" in sql
    assert "$1::uuid" in sql


def test_owner_scope_without_alias_does_not_use_sql_keyword_as_alias():
    sql = _inject_owner_scope("SELECT events.id FROM events WHERE events.event_type = 'person_entered'")
    assert "events.camera_id IN" in sql


def test_owner_scope_is_inserted_before_limit():
    sql = _inject_owner_scope("SELECT e.id FROM events e ORDER BY e.timestamp DESC LIMIT 50")
    assert sql.index("WHERE e.camera_id IN") < sql.index("ORDER BY")
    assert sql.endswith("LIMIT 50")


def test_safe_sql_allows_event_joins_but_not_account_tables():
    sql = """
        SELECT e.timestamp, p.label, o.category
        FROM events e
        LEFT JOIN persons p ON p.id = e.person_id
        LEFT JOIN tracked_objects o ON o.id = e.object_id
    """
    assert _safe_sql(sql)
