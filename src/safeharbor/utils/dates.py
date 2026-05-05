"""Date and time formatting helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Mapped


class HasTimezone(Protocol):
    """Structural type for objects that expose an IANA timezone."""

    @property
    def timezone(self) -> str | Mapped[str]:
        """Return the IANA timezone name."""


def parse_recorded_at_input(naive_str: str, tank: HasTimezone) -> datetime:
    """Parse a tank-local datetime-local value and return a UTC-aware datetime.

    Ambiguous or nonexistent local times follow the stdlib zoneinfo defaults.
    """
    if "T" not in naive_str:
        raise ValueError("recorded_at input must include a local date and time")
    parsed = datetime.fromisoformat(naive_str)
    if parsed.tzinfo is not None and parsed.utcoffset() is not None:
        raise ValueError("recorded_at input must be timezone-naive")

    tank_tz = ZoneInfo(str(tank.timezone))
    return parsed.replace(tzinfo=tank_tz).astimezone(UTC)


def tank_local_naive_now(tank: HasTimezone | None) -> datetime:
    """Return current time as a timezone-naive value for a tank-local form field."""
    now_utc = datetime.now(UTC)
    if tank is None:
        return now_utc.replace(tzinfo=None)
    return now_utc.astimezone(ZoneInfo(str(tank.timezone))).replace(tzinfo=None)


def format_recorded_at(dt_utc: datetime, tank: HasTimezone, fmt: str = "default") -> str:
    """Format a UTC datetime in the tank's local timezone."""
    if dt_utc.tzinfo is None or dt_utc.utcoffset() is None:
        raise ValueError("format_recorded_at requires an aware datetime")

    local_dt = dt_utc.astimezone(ZoneInfo(str(tank.timezone)))

    if fmt == "default":
        return local_dt.strftime("%b %-d, %Y at %-I:%M %p %Z")
    if fmt == "short":
        return local_dt.strftime("%b %-d, %-I:%M %p")
    if fmt == "iso":
        return local_dt.isoformat()

    raise ValueError(f"Unknown recorded-at format: {fmt}")
