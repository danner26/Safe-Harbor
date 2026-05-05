"""new_id() returns time-ordered uuid7 values."""

from __future__ import annotations

import time
from uuid import UUID

from safeharbor.models.base import new_id


def test_new_id_returns_uuid_instance() -> None:
    result = new_id()
    assert isinstance(result, UUID)


def test_new_id_two_calls_produce_different_values() -> None:
    a = new_id()
    b = new_id()
    assert a != b


def test_new_id_is_time_ordered() -> None:
    """uuid7 prefixes timestamp; later UUIDs sort after earlier ones."""
    earlier = new_id()
    time.sleep(0.01)
    later = new_id()
    assert str(earlier) < str(later)
