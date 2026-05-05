"""uat add tank profile

Revision ID: b7a9c2d1e4f6
Revises: 9b1c3d0f4a2e
Create Date: 2026-05-04 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b7a9c2d1e4f6"
down_revision = "9b1c3d0f4a2e"
branch_labels = None
depends_on = None

OLD_PARAMETER_RANGES_UNIQUE = "parameter_ranges_unique_per_water_type"
NEW_PARAMETER_RANGES_UNIQUE = "parameter_ranges_unique_per_water_profile"
PARAMETER_RANGES_PROFILE_IDX = "parameter_ranges_profile_param_idx"


def upgrade() -> None:
    op.add_column(
        "tanks",
        sa.Column(
            "profile_key",
            sa.String(length=64),
            server_default=sa.text("'tropical_fw_community'"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE tanks
        SET profile_key = CASE water_type
            WHEN 'salt' THEN 'reef_sw'
            WHEN 'brackish' THEN 'brackish'
            ELSE 'tropical_fw_community'
        END
        """
    )
    op.alter_column("tanks", "profile_key", server_default=None)

    op.add_column(
        "parameter_ranges",
        sa.Column(
            "profile_key",
            sa.String(length=64),
            server_default=sa.text("'tropical_fw_community'"),
            nullable=False,
        ),
    )
    op.execute(
        """
        UPDATE parameter_ranges
        SET profile_key = CASE water_type
            WHEN 'salt' THEN 'reef_sw'
            WHEN 'brackish' THEN 'brackish'
            ELSE 'tropical_fw_community'
        END
        """
    )
    op.alter_column("parameter_ranges", "profile_key", server_default=None)

    op.execute(
        "ALTER TABLE parameter_ranges "
        "DROP CONSTRAINT IF EXISTS parameter_ranges_unique_per_water_type"
    )
    op.create_unique_constraint(
        NEW_PARAMETER_RANGES_UNIQUE,
        "parameter_ranges",
        ["parameter_type_id", "water_type", "profile_key"],
    )
    op.create_index(
        PARAMETER_RANGES_PROFILE_IDX,
        "parameter_ranges",
        ["profile_key", "parameter_type_id"],
    )


def downgrade() -> None:
    op.drop_index(PARAMETER_RANGES_PROFILE_IDX, table_name="parameter_ranges")
    op.drop_constraint(
        NEW_PARAMETER_RANGES_UNIQUE,
        "parameter_ranges",
        type_="unique",
    )
    op.execute(
        """
        WITH ranked_ranges AS (
            SELECT
                id,
                row_number() OVER (
                    PARTITION BY parameter_type_id, water_type
                    ORDER BY
                        CASE
                            WHEN profile_key = 'tropical_fw_community' THEN 0
                            ELSE 1
                        END,
                        id
                ) AS row_num
            FROM parameter_ranges
        )
        DELETE FROM parameter_ranges
        WHERE id IN (
            SELECT id
            FROM ranked_ranges
            WHERE row_num > 1
        )
        """
    )
    op.create_unique_constraint(
        OLD_PARAMETER_RANGES_UNIQUE,
        "parameter_ranges",
        ["parameter_type_id", "water_type"],
    )
    op.drop_column("parameter_ranges", "profile_key")
    op.drop_column("tanks", "profile_key")
