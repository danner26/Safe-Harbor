"""EmailChangeToken model - pending single-use email update tokens."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, new_id


class EmailChangeToken(Base):
    __tablename__ = "email_change_tokens"
    __table_args__ = (
        CheckConstraint(
            "used_at IS NULL OR used_at >= created_at",
            name="email_change_tokens_used_at_after_created_at_check",
        ),
        Index(
            "email_change_tokens_user_pending_idx",
            "user_id",
            "used_at",
            postgresql_where=text("used_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    new_email: Mapped[str] = mapped_column(String(254), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )

    def __repr__(self) -> str:
        return f"<EmailChangeToken id={self.id} user_id={self.user_id}>"
