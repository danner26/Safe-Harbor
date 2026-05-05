"""add uploads and settings schema

Revision ID: cf2f4d7a9b31
Revises: a8f2d4c9e671
Create Date: 2026-04-29 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'cf2f4d7a9b31'
down_revision = 'a8f2d4c9e671'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(length=64), nullable=False),
        sa.Column('value', sa.String(length=256), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_by_user_id', sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('key'),
    )
    op.execute(
        "INSERT INTO system_settings (key, value) "
        "VALUES ('email_verify_on_change', 'true')"
    )

    op.create_table(
        'email_change_tokens',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('new_email', sa.String(length=254), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint(
            'used_at IS NULL OR used_at >= created_at',
            name='email_change_tokens_used_at_after_created_at_check',
        ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token'),
    )
    op.create_index(
        'email_change_tokens_user_pending_idx',
        'email_change_tokens',
        ['user_id', 'used_at'],
        unique=False,
        postgresql_where=sa.text('used_at IS NULL'),
    )

    op.add_column('users', sa.Column('theme_pref', sa.String(length=8), nullable=True))
    op.add_column('users', sa.Column('date_format_pref', sa.String(length=8), nullable=True))
    op.create_check_constraint(
        'users_theme_pref_check',
        'users',
        "theme_pref IS NULL OR theme_pref IN ('light', 'dark')",
    )
    op.create_check_constraint(
        'users_date_format_pref_check',
        'users',
        "date_format_pref IS NULL OR date_format_pref IN ('us', 'iso')",
    )


def downgrade():
    op.drop_constraint('users_date_format_pref_check', 'users', type_='check')
    op.drop_constraint('users_theme_pref_check', 'users', type_='check')
    op.drop_column('users', 'date_format_pref')
    op.drop_column('users', 'theme_pref')

    op.drop_index(
        'email_change_tokens_user_pending_idx',
        table_name='email_change_tokens',
        postgresql_where=sa.text('used_at IS NULL'),
    )
    op.drop_table('email_change_tokens')
    op.drop_table('system_settings')
