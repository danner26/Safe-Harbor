"""ParameterRange — advisory min/max bounds per (parameter_type, water_type).

Seeded with v1 defaults (ATM Reef + API Freshwater chart approximations).
Used in Phase 1c.3 for out-of-range badges; lands in 1c.2 only as data."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, TimestampMixin, new_id


class ParameterRange(Base, TimestampMixin):
    __tablename__ = "parameter_ranges"
    __table_args__ = (
        CheckConstraint(
            "water_type IN ('fresh', 'salt', 'brackish')",
            name="parameter_ranges_water_type_check",
        ),
        UniqueConstraint(
            "parameter_type_id",
            "water_type",
            "profile_key",
            name="parameter_ranges_unique_per_water_profile",
        ),
        Index(
            "parameter_ranges_profile_param_idx",
            "profile_key",
            "parameter_type_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    parameter_type_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("parameter_types.id"), nullable=False
    )
    water_type: Mapped[str] = mapped_column(String(16), nullable=False)
    profile_key: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'tropical_fw_community'")
    )
    min_value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    max_value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    stale_after_days: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ParameterRange parameter_type_id={self.parameter_type_id} "
            f"water_type={self.water_type} {self.min_value}-{self.max_value}>"
        )
