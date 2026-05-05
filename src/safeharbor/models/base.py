"""Declarative base, timestamp mixin, and uuid7 ID helper.

`new_id()` is the only place uuid7 generation lives; swap implementations here
without touching every model."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import uuid_utils
from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column


class Base(DeclarativeBase):
    """Project-wide SQLAlchemy 2.0 declarative base."""


class TimestampMixin:
    """Adds `created_at` and `updated_at` columns; both default to now()."""

    @declared_attr.directive
    def created_at(cls) -> Mapped[datetime]:  # noqa: N805
        return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    @declared_attr.directive
    def updated_at(cls) -> Mapped[datetime]:  # noqa: N805
        return mapped_column(
            DateTime(timezone=True),
            server_default=func.now(),
            onupdate=func.now(),
            nullable=False,
        )


def new_id() -> UUID:
    """Return a time-ordered uuid7 (RFC 9562) for use as a primary key.

    Isolated here so we can swap the underlying implementation without touching
    model definitions."""
    return UUID(str(uuid_utils.uuid7()))
