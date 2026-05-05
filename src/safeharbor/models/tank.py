"""Tank model — aquariums tracked by the install. Soft-delete via decommission_date."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, Numeric, String, text
from sqlalchemy.dialects.postgresql import UUID as PgUUID  # noqa: N811
from sqlalchemy.orm import Mapped, mapped_column

from safeharbor.models.base import Base, TimestampMixin, new_id


class WaterType(StrEnum):
    FRESH = "fresh"
    SALT = "salt"
    BRACKISH = "brackish"


TANK_PROFILES: tuple[str, ...] = (
    "tropical_fw_community",
    "coldwater_fw",
    "planted_fw",
    "reef_sw",
    "fowlr_sw",
    "brackish",
)

PROFILE_WATER_TYPES = {
    "tropical_fw_community": "fresh",
    "coldwater_fw": "fresh",
    "planted_fw": "fresh",
    "reef_sw": "salt",
    "fowlr_sw": "salt",
    "brackish": "brackish",
}


def profiles_for_water_type(water_type: str) -> list[str]:
    """Return tank profile keys applicable to the requested water type."""
    return [
        profile_key
        for profile_key in TANK_PROFILES
        if PROFILE_WATER_TYPES.get(profile_key) == water_type
    ]


class Tank(Base, TimestampMixin):
    __tablename__ = "tanks"
    __table_args__ = (
        CheckConstraint(
            "water_type IN ('fresh', 'salt', 'brackish')",
            name="tanks_water_type_check",
        ),
        Index(
            "tanks_active_idx",
            "created_at",
            postgresql_where=text("decommission_date IS NULL"),
        ),
        Index(
            "tanks_decommissioned_idx",
            "decommission_date",
            postgresql_where=text("decommission_date IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    water_type: Mapped[str] = mapped_column(String(16), nullable=False)
    profile_key: Mapped[str] = mapped_column(
        String(64), nullable=False, server_default=text("'tropical_fw_community'")
    )
    volume_liters: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    setup_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    decommission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    substrate: Mapped[str | None] = mapped_column(String(256), nullable=True)
    equipment_notes: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String, nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, server_default=text("'UTC'"))
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<Tank id={self.id} name={self.name} water_type={self.water_type}>"
