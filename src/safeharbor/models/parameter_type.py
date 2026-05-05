"""ParameterType — water-quality parameter registry. Seeded; not user-editable in v1."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, TimestampMixin, new_id


class ParameterType(Base, TimestampMixin):
    __tablename__ = "parameter_types"
    __table_args__ = (
        CheckConstraint(
            "applies_to_water_type IS NULL OR "
            "applies_to_water_type IN ('fresh', 'salt', 'brackish')",
            name="parameter_types_water_type_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    key: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    canonical_unit_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("units.id"), nullable=False
    )
    applies_to_water_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    def __repr__(self) -> str:
        return f"<ParameterType key={self.key}>"
