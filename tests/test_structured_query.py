"""Tests for the no-LLM event search fallback."""

from datetime import timedelta

from structured_query import build_fallback_query


def test_fallback_query_searches_item_and_today():
    sql, params = build_fallback_query("did john pick up my keys today?")
    assert "FROM events e" in sql
    assert "owner_id" not in sql
    assert "o.category ILIKE $2" in sql
    assert "p.label ILIKE $3" in sql
    assert params[0] == "%keys%"
    assert params[1] == "%john%"
    assert params[2].tzinfo is not None


def test_fallback_query_uses_yesterday_range_without_interpolating_text():
    sql, params = build_fallback_query("where was my wallet yesterday?")
    assert "e.timestamp >= $3" in sql
    assert "e.timestamp < $4" in sql
    assert "%wallet%" in params
    assert len(params) == 3


def test_fallback_query_does_not_require_a_search_term():
    sql, params = build_fallback_query("what happened today?")
    assert "e.timestamp >= $2" in sql
    assert params[0].tzinfo is not None


def test_fallback_query_maps_detector_alias_to_object_category():
    sql, params = build_fallback_query("where were my scissors today?")
    assert "o.category ILIKE $2" in sql
    assert params[0] == "%tool%"
    assert "p.label ILIKE" not in sql


def test_fallback_query_supports_custom_toolbox_category():
    sql, params = build_fallback_query("where was my toolbox today?")
    assert "o.category ILIKE $2" in sql
    assert params[0] == "%toolbox%"


def test_fallback_query_filters_location_and_day_part():
    sql, params = build_fallback_query(
        "what happened in the garage this afternoon?"
    )
    assert "e.location_label ILIKE $2" in sql
    assert "e.timestamp >= $3" in sql
    assert "e.timestamp <= $4" in sql
    assert params[0] == "%garage%"
    assert params[1].hour == 12
    assert params[2].hour == 18
    assert "p.label ILIKE" not in sql


def test_fallback_query_filters_an_exact_clock_minute():
    sql, params = build_fallback_query("who grabbed my keys at 4:30 pm?")
    assert "o.category ILIKE $2" in sql
    assert "e.timestamp >= $3" in sql
    assert "e.timestamp < $4" in sql
    assert params[1].hour == 16
    assert params[1].minute == 30
    assert params[2] - params[1] == timedelta(minutes=1)
    assert "p.label ILIKE" not in sql


def test_fallback_query_supports_24_hour_clock():
    _, params = build_fallback_query("what happened at 21:05 yesterday?")
    assert params[0].hour == 21
    assert params[0].minute == 5
    assert params[1] - params[0] == timedelta(minutes=1)
