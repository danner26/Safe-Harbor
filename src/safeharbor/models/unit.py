"""Unit model — display unit registry. Seeded; not user-editable in v1."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, TimestampMixin, new_id


class UnitDimension(StrEnum):
    TEMPERATURE = "temperature"
    CONCENTRATION = "concentration"
    SALINITY = "salinity"
    ALKALINITY = "alkalinity"
    HARDNESS = "hardness"
    DIMENSIONLESS = "dimensionless"


class Unit(Base, TimestampMixin):
    __tablename__ = "units"
    __table_args__ = (
        CheckConstraint(
            "dimension IN ('temperature', 'concentration', 'salinity', "
            "'alkalinity', 'hardness', 'dimensionless')",
            name="units_dimension_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    display: Mapped[str] = mapped_column(String(8), nullable=False)
    dimension: Mapped[str] = mapped_column(String(16), nullable=False)

    def __repr__(self) -> str:
        return f"<Unit code={self.code} dimension={self.dimension}>"
