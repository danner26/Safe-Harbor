"""Invite model — single-use token rows for admin-issued registrations and password resets."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, TimestampMixin, new_id


class InviteKind(StrEnum):
    INVITE = "invite"
    PASSWORD_RESET = "password_reset"


class Invite(Base, TimestampMixin):
    __tablename__ = "invites"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('invite', 'password_reset')",
            name="invites_kind_check",
        ),
        Index(
            "invites_kind_active_idx",
            "kind",
            postgresql_where=text("consumed_at IS NULL"),
        ),
        Index("invites_email_idx", "email"),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    issued_by: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Invite id={self.id} kind={self.kind} email={self.email}>"
