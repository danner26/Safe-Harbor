"""tank_timezone_and_stale_thresholds

Adds tanks.timezone (IANA name, defaulted from DEFAULT_TZ env at upgrade time
or UTC as fallback), parameter_ranges.stale_after_days (per-parameter staleness
thresholds with reasonable defaults), and drops the legacy tanks.status check
constraint + column in favor of a derived rollup.

Revision ID: 9b1c3d0f4a2e
Revises: cf2f4d7a9b31
Create Date: 2026-05-01 00:00:00.000000

"""

from __future__ import annotations

import os
import zoneinfo

import sqlalchemy as sa
from alembic import op

revision = "9b1c3d0f4a2e"
down_revision = "cf2f4d7a9b31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parameter_ranges",
        sa.Column(
            "stale_after_days",
            sa.Integer(),
            server_default=sa.text("7"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE parameter_ranges
        SET stale_after_days = 7
        WHERE parameter_type_id IN (
            SELECT id FROM parameter_types
            WHERE key IN ('temperature', 'ph', 'salinity', 'ammonia', 'nitrite')
        )
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges
        SET stale_after_days = 14
        WHERE parameter_type_id IN (
            SELECT id FROM parameter_types
            WHERE key IN ('nitrate', 'phosphate')
        )
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges
        SET stale_after_days = 30
        WHERE parameter_type_id IN (
            SELECT id FROM parameter_types
            WHERE key IN ('kh', 'gh', 'calcium', 'magnesium')
        )
        """
    )
    op.alter_column("parameter_ranges", "stale_after_days", server_default=None)

    op.add_column(
        "tanks",
        sa.Column(
            "timezone",
            sa.String(length=64),
            server_default=sa.text("'UTC'"),
            nullable=False,
        ),
    )
    env_tz = os.environ.get("DEFAULT_TZ", "").strip()
    if env_tz:
        try:
            zoneinfo.ZoneInfo(env_tz)
            default_tz = env_tz
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            default_tz = "UTC"
    else:
        default_tz = "UTC"

    op.get_bind().execute(
        sa.text("UPDATE tanks SET timezone = COALESCE(NULLIF(:default_tz, ''), 'UTC')"),
        {"default_tz": default_tz},
    )

    op.execute("ALTER TABLE tanks DROP CONSTRAINT IF EXISTS tanks_status_check")
    op.drop_column("tanks", "status")


def downgrade() -> None:
    op.add_column(
        "tanks",
        sa.Column(
            "status",
            sa.String(length=16),
            server_default=sa.text("'unknown'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "tanks_status_check",
        "tanks",
        "status IN ('healthy', 'watch', 'unhealthy', 'unknown')",
    )
    op.drop_column("tanks", "timezone")
    op.drop_column("parameter_ranges", "stale_after_days")
