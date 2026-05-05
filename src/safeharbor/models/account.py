"""User model — the only Identity table in the single-tenant core."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from flask_login import UserMixin
from sqlalchemy import Boolean, CheckConstraint, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, TimestampMixin, new_id


class UnitsPref(StrEnum):
    IMPERIAL = "imperial"
    METRIC = "metric"


class User(UserMixin, Base, TimestampMixin):  # type: ignore[misc]
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "theme_pref IS NULL OR theme_pref IN ('light', 'dark')",
            name="users_theme_pref_check",
        ),
        CheckConstraint(
            "date_format_pref IS NULL OR date_format_pref IN ('us', 'iso')",
            name="users_date_format_pref_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_superuser: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    preferred_units: Mapped[str | None] = mapped_column(String(16), nullable=True)
    theme_pref: Mapped[str | None] = mapped_column(String(8), nullable=True)
    date_format_pref: Mapped[str | None] = mapped_column(String(8), nullable=True)
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def display_username(self) -> str:
        username = self.username or ""
        if username:
            return username

        email_prefix = self.email.partition("@")[0]
        return email_prefix or "user"

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"
