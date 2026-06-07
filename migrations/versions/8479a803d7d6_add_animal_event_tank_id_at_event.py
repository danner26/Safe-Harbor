"""add animal_event tank_id_at_event

Revision ID: 8479a803d7d6
Revises: b7a9c2d1e4f6
Create Date: 2026-06-06 19:39:16.543382

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '8479a803d7d6'
down_revision = 'b7a9c2d1e4f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Add column nullable for the backfill window
    op.add_column(
        "animal_events",
        sa.Column(
            "tank_id_at_event",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tanks.id"),
            nullable=True,
        ),
    )

    # 2a. Backfill pinned events (acquired, moved) -- tank_id_at_event == tank_id
    op.execute(
        "UPDATE animal_events SET tank_id_at_event = tank_id WHERE tank_id IS NOT NULL"
    )

    # 2b. Backfill non-pinned events -- most-recent prior pinned event's tank_id
    op.execute(
        """
        UPDATE animal_events e SET tank_id_at_event = (
          SELECT p.tank_id FROM animal_events p
          WHERE p.animal_id = e.animal_id
            AND p.tank_id IS NOT NULL
            AND (
              p.occurred_at < e.occurred_at
              OR (
                p.occurred_at = e.occurred_at
                AND (
                  p.created_at < e.created_at
                  OR (p.created_at = e.created_at AND p.id <= e.id)
                )
              )
            )
          ORDER BY p.occurred_at DESC, p.created_at DESC, p.id DESC
          LIMIT 1
        )
        WHERE e.tank_id IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("animal_events", "tank_id_at_event")
