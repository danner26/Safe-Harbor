"""parameter range directionality and value corrections

Revision ID: 9a3e6e39e4eb
Revises: 8479a803d7d6
Create Date: 2026-06-07 00:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "9a3e6e39e4eb"
down_revision = "8479a803d7d6"
branch_labels = None
depends_on = None

PARAMETER_RANGES_DIRECTIONALITY_CHECK = "parameter_ranges_directionality_check"


def upgrade() -> None:
    op.add_column(
        "parameter_ranges",
        sa.Column(
            "directionality",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'range'"),
        ),
    )
    op.create_check_constraint(
        PARAMETER_RANGES_DIRECTIONALITY_CHECK,
        "parameter_ranges",
        "directionality IN ('range','lower_better','higher_better')",
    )

    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET directionality = 'lower_better'
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key IN ('ammonia', 'nitrite')
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET directionality = 'lower_better'
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key IN ('nitrate', 'phosphate')
          AND pr.profile_key IN (
              'tropical_fw_community',
              'coldwater_fw',
              'fowlr_sw',
              'brackish'
          )
        """
    )

    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 18.0, max_value = 23.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'temperature'
          AND pr.profile_key = 'coldwater_fw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 7.0, max_value = 8.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'ph'
          AND pr.profile_key = 'coldwater_fw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 5.0, max_value = 50.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'nitrate'
          AND pr.profile_key = 'planted_fw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 0.5, max_value = 2.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'phosphate'
          AND pr.profile_key = 'planted_fw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 34.0, max_value = 36.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'salinity'
          AND pr.profile_key = 'reef_sw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 1.0, max_value = 10.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'nitrate'
          AND pr.profile_key = 'reef_sw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 0.02, max_value = 0.10
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'phosphate'
          AND pr.profile_key = 'reef_sw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 400, max_value = 450
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'calcium'
          AND pr.profile_key = 'reef_sw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 23.0, max_value = 28.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'temperature'
          AND pr.profile_key = 'brackish'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 7.5, max_value = 8.4
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'ph'
          AND pr.profile_key = 'brackish'
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 18.3, max_value = 22.2
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'temperature'
          AND pr.profile_key = 'coldwater_fw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 6.8, max_value = 7.6
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'ph'
          AND pr.profile_key = 'coldwater_fw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 0, max_value = 20.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'nitrate'
          AND pr.profile_key = 'planted_fw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 0, max_value = 0.5
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'phosphate'
          AND pr.profile_key = 'planted_fw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 33.0, max_value = 35.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'salinity'
          AND pr.profile_key = 'reef_sw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 0, max_value = 5.0
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'nitrate'
          AND pr.profile_key = 'reef_sw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 0, max_value = 0.05
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'phosphate'
          AND pr.profile_key = 'reef_sw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 380, max_value = 450
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'calcium'
          AND pr.profile_key = 'reef_sw'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 23.9, max_value = 26.7
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'temperature'
          AND pr.profile_key = 'brackish'
        """
    )
    op.execute(
        """
        UPDATE parameter_ranges AS pr
        SET min_value = 7.4, max_value = 8.2
        FROM parameter_types AS pt
        WHERE pr.parameter_type_id = pt.id
          AND pt.key = 'ph'
          AND pr.profile_key = 'brackish'
        """
    )

    op.drop_constraint(
        PARAMETER_RANGES_DIRECTIONALITY_CHECK,
        "parameter_ranges",
        type_="check",
    )
    op.drop_column("parameter_ranges", "directionality")
