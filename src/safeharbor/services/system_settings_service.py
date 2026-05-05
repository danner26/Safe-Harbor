"""System settings service - caller-committed helpers for global settings."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from safeharbor.extensions import db
from safeharbor.models.system_setting import SystemSetting


def _get_value(key: str) -> str | None:
    """Return the raw stored setting value, or None when no row exists."""
    setting = db.session.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if setting is None:
        return None

    value: str = setting.value
    return value


def get_bool(key: str, default: bool) -> bool:
    """Return a boolean setting value, or default when no row exists."""
    value = _get_value(key)
    if value is None:
        return default

    if value == "true":
        return True
    if value == "false":
        return False

    raise ValueError(f"System setting {key!r} must be 'true' or 'false', got {value!r}.")


def get_str(key: str, default: str) -> str:
    """Return a string setting value, or default when no row exists."""
    value = _get_value(key)
    if value is None:
        return default

    return value


def set_value(*, key: str, value: str, updated_by_user_id: UUID | None) -> None:
    """Create or update a setting row without committing the transaction."""
    setting = db.session.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if setting is None:
        setting = SystemSetting(
            key=key,
            value=value,
            updated_by_user_id=updated_by_user_id,
        )
        db.session.add(setting)
    else:
        setting.value = value
        setting.updated_by_user_id = updated_by_user_id

    db.session.flush()
