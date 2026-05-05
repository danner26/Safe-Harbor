"""Tests for recorded-at input parsing."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from safeharbor.utils.dates import parse_recorded_at_input


def test_est_string_converts_to_utc() -> None:
    """A winter New York input is interpreted as EST and converted to UTC."""
    tank = SimpleNamespace(timezone="America/New_York")

    result = parse_recorded_at_input("2026-01-01T14:00", tank)

    assert result == datetime(2026, 1, 1, 19, 0, tzinfo=UTC)


def test_pst_string_converts_to_utc() -> None:
    """A winter Los Angeles input is interpreted as PST and converted to UTC."""
    tank = SimpleNamespace(timezone="America/Los_Angeles")

    result = parse_recorded_at_input("2026-01-01T14:00", tank)

    assert result == datetime(2026, 1, 1, 22, 0, tzinfo=UTC)


def test_dst_spring_forward_in_tank_tz() -> None:
    """The tank timezone's post-transition offset is used after spring forward."""
    tank = SimpleNamespace(timezone="America/New_York")

    result = parse_recorded_at_input("2026-03-08T03:30", tank)

    assert result == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)


def test_tz_aware_input_rejected() -> None:
    """Timezone-aware input is rejected instead of being silently converted."""
    tank = SimpleNamespace(timezone="America/New_York")

    with pytest.raises(ValueError):
        parse_recorded_at_input("2026-05-01T14:00+00:00", tank)


def test_date_only_input_raises_value_error() -> None:
    """Date-only input is rejected instead of becoming midnight."""
    tank = SimpleNamespace(timezone="America/New_York")

    with pytest.raises(ValueError):
        parse_recorded_at_input("2026-05-01", tank)


def test_invalid_isoformat_raises_value_error() -> None:
    """Invalid datetime input raises ValueError from ISO parsing."""
    tank = SimpleNamespace(timezone="America/New_York")

    with pytest.raises(ValueError):
        parse_recorded_at_input("not-a-datetime", tank)
