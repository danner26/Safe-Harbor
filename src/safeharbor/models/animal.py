"""Animal model - livestock tracked by the install."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, TimestampMixin, new_id


class Sex(StrEnum):
    MALE = "male"
    FEMALE = "female"
    UNKNOWN = "unknown"


class Animal(Base, TimestampMixin):
    __tablename__ = "animals"
    __table_args__ = (
        CheckConstraint(
            "sex IN ('male', 'female', 'unknown')",
            name="animals_sex_check",
        ),
        CheckConstraint(
            "acquired_quantity >= 1",
            name="animals_acquired_quantity_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    species: Mapped[str] = mapped_column(String(64), nullable=False)
    scientific_name: Mapped[str | None] = mapped_column(String(96), nullable=True)
    sex: Mapped[str | None] = mapped_column(String(16), nullable=True)
    acquired_quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(256), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(512), nullable=True)
