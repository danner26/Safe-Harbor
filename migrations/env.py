"""Alembic migration environment for Safe Harbor."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from flask import current_app

# Ensure all models are imported so MetaData is populated for autogenerate.
from safeharbor import models  # noqa: F401

config = context.config
fileConfig(config.config_file_name)

config.set_main_option(
    "sqlalchemy.url",
    str(current_app.extensions["migrate"].db.engine.url).replace("%", "%%"),
)
target_metadata = current_app.extensions["migrate"].db.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = current_app.extensions["migrate"].db.engine
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
