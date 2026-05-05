"""Tests for tank-local datetime formatting."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from safeharbor.utils.dates import format_recorded_at, tank_local_naive_now


def test_default_format_renders_tz_name() -> None:
    tank = SimpleNamespace(timezone="America/New_York")
    dt_utc = datetime(2026, 1, 15, 18, 5, tzinfo=UTC)

    assert format_recorded_at(dt_utc, tank) == "Jan 15, 2026 at 1:05 PM EST"


def test_short_format_omits_tz_suffix() -> None:
    tank = SimpleNamespace(timezone="America/New_York")
    dt_utc = datetime(2026, 1, 15, 18, 5, tzinfo=UTC)

    assert format_recorded_at(dt_utc, tank, fmt="short") == "Jan 15, 1:05 PM"


def test_iso_format_includes_offset() -> None:
    tank = SimpleNamespace(timezone="America/New_York")
    dt_utc = datetime(2026, 1, 15, 18, 5, tzinfo=UTC)

    assert format_recorded_at(dt_utc, tank, fmt="iso") == "2026-01-15T13:05:00-05:00"


def test_dst_spring_forward_renders_correct_offset() -> None:
    tank = SimpleNamespace(timezone="America/New_York")
    dt_utc = datetime(2026, 3, 8, 7, 30, tzinfo=UTC)

    assert format_recorded_at(dt_utc, tank) == "Mar 8, 2026 at 3:30 AM EDT"


def test_dst_fall_back_uses_fold_zero() -> None:
    tank = SimpleNamespace(timezone="America/New_York")
    dt_utc = datetime(2026, 11, 1, 5, 30, tzinfo=UTC)

    assert format_recorded_at(dt_utc, tank) == "Nov 1, 2026 at 1:30 AM EDT"


def test_naive_input_raises_value_error() -> None:
    tank = SimpleNamespace(timezone="America/New_York")
    dt_naive = datetime(2026, 1, 15, 18, 5)

    with pytest.raises(ValueError, match="aware datetime"):
        format_recorded_at(dt_naive, tank)


def test_tank_local_naive_now_returns_naive_in_tank_tz() -> None:
    tank = SimpleNamespace(timezone="America/Los_Angeles")

    before = datetime.now(UTC)
    result = tank_local_naive_now(tank)
    after = datetime.now(UTC)

    assert result.tzinfo is None
    expected_start = before.astimezone(ZoneInfo(tank.timezone)).replace(tzinfo=None)
    expected_end = after.astimezone(ZoneInfo(tank.timezone)).replace(tzinfo=None)
    assert expected_start - timedelta(seconds=1) <= result <= expected_end + timedelta(seconds=1)


def test_tank_local_naive_now_fallback_without_tank_is_utc_naive() -> None:
    before = datetime.now(UTC)
    result = tank_local_naive_now(None)
    after = datetime.now(UTC)

    assert result.tzinfo is None
    assert (
        before.replace(tzinfo=None) - timedelta(seconds=1)
        <= result
        <= after.replace(tzinfo=None) + timedelta(seconds=1)
    )
