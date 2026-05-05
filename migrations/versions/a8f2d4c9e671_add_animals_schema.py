"""add animals schema

Revision ID: a8f2d4c9e671
Revises: 4bc6ca63a200
Create Date: 2026-04-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a8f2d4c9e671'
down_revision = '4bc6ca63a200'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'animals',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=64), nullable=True),
        sa.Column('species', sa.String(length=64), nullable=False),
        sa.Column('scientific_name', sa.String(length=96), nullable=True),
        sa.Column('sex', sa.String(length=16), nullable=True),
        sa.Column('acquired_quantity', sa.Integer(), nullable=False),
        sa.Column('image_path', sa.String(length=256), nullable=True),
        sa.Column('notes', sa.String(length=512), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "sex IN ('male', 'female', 'unknown')",
            name='animals_sex_check',
        ),
        sa.CheckConstraint(
            'acquired_quantity >= 1',
            name='animals_acquired_quantity_check',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'animal_events',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('animal_id', sa.UUID(), nullable=False),
        sa.Column('event_type', sa.String(length=16), nullable=False),
        sa.Column('tank_id', sa.UUID(), nullable=True),
        sa.Column('quantity_delta', sa.Integer(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('note', sa.String(length=512), nullable=True),
        sa.Column('recorded_by_user_id', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
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
            name='animal_events_event_type_rules_check',
        ),
        sa.ForeignKeyConstraint(['animal_id'], ['animals.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['tank_id'], ['tanks.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        "CREATE INDEX animal_events_animal_occurred_idx "
        "ON animal_events (animal_id, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX animal_events_tank_occurred_idx "
        "ON animal_events (tank_id, occurred_at DESC) "
        "WHERE tank_id IS NOT NULL"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS animal_events_tank_occurred_idx")
    op.execute("DROP INDEX IF EXISTS animal_events_animal_occurred_idx")
    op.drop_table('animal_events')
    op.drop_table('animals')
