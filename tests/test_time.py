"""Shared time-zone behavior tests."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import omniscient_shared.time as time_utils


def test_to_local_converts_aware_timestamp(monkeypatch):
    monkeypatch.setattr(time_utils, "LOCAL_TIMEZONE", ZoneInfo("America/New_York"))
    converted = time_utils.to_local(datetime(2026, 7, 1, 16, 30, tzinfo=UTC))
    assert converted.hour == 12
    assert converted.tzinfo == ZoneInfo("America/New_York")


def test_to_local_treats_naive_timestamp_as_utc(monkeypatch):
    monkeypatch.setattr(time_utils, "LOCAL_TIMEZONE", ZoneInfo("America/New_York"))
    converted = time_utils.to_local(datetime(2026, 1, 1, 16, 30))
    assert converted.hour == 11
