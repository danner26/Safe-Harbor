"""add measurements schema

Revision ID: 4bc6ca63a200
Revises: 2d77fe37aaa6
Create Date: 2026-04-28 19:33:00.118887

"""
from alembic import op
import sqlalchemy as sa


revision = '4bc6ca63a200'
down_revision = '2d77fe37aaa6'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'units',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('code', sa.String(length=16), nullable=False),
        sa.Column('display', sa.String(length=8), nullable=False),
        sa.Column('dimension', sa.String(length=16), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "dimension IN ('temperature', 'concentration', 'salinity', 'alkalinity', 'hardness', 'dimensionless')",
            name='units_dimension_check',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_table(
        'parameter_types',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('key', sa.String(length=32), nullable=False),
        sa.Column('display_name', sa.String(length=64), nullable=False),
        sa.Column('canonical_unit_id', sa.UUID(), nullable=False),
        sa.Column('applies_to_water_type', sa.String(length=16), nullable=True),
        sa.Column('display_order', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "applies_to_water_type IS NULL OR applies_to_water_type IN ('fresh', 'salt', 'brackish')",
            name='parameter_types_water_type_check',
        ),
        sa.ForeignKeyConstraint(['canonical_unit_id'], ['units.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key'),
    )
    op.create_table(
        'parameter_ranges',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('parameter_type_id', sa.UUID(), nullable=False),
        sa.Column('water_type', sa.String(length=16), nullable=False),
        sa.Column('min_value', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('max_value', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('source', sa.String(length=128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "water_type IN ('fresh', 'salt', 'brackish')",
            name='parameter_ranges_water_type_check',
        ),
        sa.ForeignKeyConstraint(['parameter_type_id'], ['parameter_types.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('parameter_type_id', 'water_type', name='parameter_ranges_unique_per_water_type'),
    )
    op.create_table(
        'measurements',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('tank_id', sa.UUID(), nullable=False),
        sa.Column('parameter_type_id', sa.UUID(), nullable=False),
        sa.Column('value', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('source', sa.String(length=8), server_default=sa.text("'manual'"), nullable=False),
        sa.Column('device_id', sa.UUID(), nullable=True),
        sa.Column('raw_value', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('raw_unit_id', sa.UUID(), nullable=True),
        sa.Column('import_job_id', sa.UUID(), nullable=True),
        sa.Column('recorded_by_user_id', sa.UUID(), nullable=True),
        sa.Column('note', sa.String(length=256), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            "source IN ('manual', 'sensor', 'import')",
            name='measurements_source_check',
        ),
        sa.ForeignKeyConstraint(['parameter_type_id'], ['parameter_types.id']),
        sa.ForeignKeyConstraint(['raw_unit_id'], ['units.id']),
        sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['tank_id'], ['tanks.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.execute(
        "CREATE INDEX measurements_tank_param_recorded_idx "
        "ON measurements (tank_id, parameter_type_id, recorded_at DESC)"
    )
    op.execute(
        "CREATE INDEX measurements_recorded_idx ON measurements (recorded_at DESC)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS measurements_recorded_idx")
    op.execute("DROP INDEX IF EXISTS measurements_tank_param_recorded_idx")
    op.drop_table('measurements')
    op.drop_table('parameter_ranges')
    op.drop_table('parameter_types')
    op.drop_table('units')
