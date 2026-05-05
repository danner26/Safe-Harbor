"""Measurement — water-quality reading. The fact table.

Replaces the legacy app's 11 parameter-specific tables. Indexed by
(tank_id, parameter_type_id, recorded_at DESC) — the access path for
KPI strip + chart queries. device_id/import_job_id columns land NULL;
their FKs land in Phase 3 (devices) and Phase 4 (import_jobs)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, TimestampMixin, new_id


class MeasurementSource(StrEnum):
    MANUAL = "manual"
    SENSOR = "sensor"
    IMPORT = "import"


class Measurement(Base, TimestampMixin):
    __tablename__ = "measurements"
    __table_args__ = (
        CheckConstraint(
            "source IN ('manual', 'sensor', 'import')",
            name="measurements_source_check",
        ),
        Index(
            "measurements_tank_param_recorded_idx",
            "tank_id",
            "parameter_type_id",
            text("recorded_at DESC"),
        ),
        Index(
            "measurements_recorded_idx",
            text("recorded_at DESC"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    tank_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tanks.id"), nullable=False
    )
    parameter_type_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("parameter_types.id"), nullable=False
    )
    value: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(8), nullable=False, server_default=text("'manual'"))
    # Phase 3 will add a FK; for 1c.2 the column lands NULL.
    device_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    raw_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    raw_unit_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("units.id"), nullable=True
    )
    # Phase 4 will add a FK; for 1c.2 the column lands NULL.
    import_job_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(String(256), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Measurement id={self.id} tank_id={self.tank_id} "
            f"parameter_type_id={self.parameter_type_id} value={self.value}>"
        )
