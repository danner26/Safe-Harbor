"""AnimalEvent model - lifecycle history entries for tracked livestock."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, new_id


class EventType(StrEnum):
    ACQUIRED = "acquired"
    MOVED = "moved"
    DECEASED = "deceased"
    HEALTH_NOTE = "health_note"
    OBSERVATION = "observation"


class AnimalEvent(Base):
    __tablename__ = "animal_events"
    __table_args__ = (
        CheckConstraint(
            """
            (
                event_type = 'acquired'
                AND tank_id IS NOT NULL
                AND quantity_delta IS NOT NULL
                AND quantity_delta > 0
            )
            OR (
                event_type = 'moved'
                AND tank_id IS NOT NULL
                AND quantity_delta IS NULL
            )
            OR (
                event_type = 'deceased'
                AND tank_id IS NULL
                AND quantity_delta IS NOT NULL
                AND quantity_delta < 0
            )
            OR (
                event_type IN ('health_note', 'observation')
                AND tank_id IS NULL
                AND quantity_delta IS NULL
            )
            """,
            name="animal_events_event_type_rules_check",
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    animal_id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("animals.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    tank_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tanks.id"), nullable=True
    )
    quantity_delta: Mapped[int | None] = mapped_column(Integer, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    recorded_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<AnimalEvent id={self.id} animal_id={self.animal_id} event_type={self.event_type}>"
