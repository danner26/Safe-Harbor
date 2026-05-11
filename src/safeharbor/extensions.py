"""Flask extension singletons.

Created uninitialized at module level; `create_app()` calls `init_app()` on each
to bind them to the application instance. This pattern keeps the app factory
clean and lets blueprints import these directly without circular imports."""

from __future__ import annotations

import importlib.metadata
import os

import sentry_sdk
from flask import Flask
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from redis import Redis
from rq import Queue
from sentry_sdk.integrations.flask import FlaskIntegration

from safeharbor.models.base import Base

_SAFEHARBOR_VERSION_FALLBACK = "0.1.0"

# Pass our custom DeclarativeBase so db.metadata == Base.metadata; models
# registered there are visible to db.create_all() and Flask-Migrate.
db = SQLAlchemy(model_class=Base)
migrate = Migrate()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message_category = "warning"
csrf = CSRFProtect()

# RQ singletons; bound to a real Redis connection in create_app()
redis_conn: Redis | None = None
default_queue: Queue | None = None


def _package_version() -> str:
    try:
        return importlib.metadata.version("safeharbor")
    except importlib.metadata.PackageNotFoundError:
        return _SAFEHARBOR_VERSION_FALLBACK


def init_sentry(app: Flask) -> None:
    """Initialize Sentry when a DSN is configured."""
    dsn = app.config["SENTRY_DSN"]
    if not dsn:
        return

    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        environment=app.config.get("FLASK_CONFIG", os.getenv("FLASK_CONFIG", "production")),
        traces_sample_rate=app.config["SENTRY_TRACES_SAMPLE_RATE"],
        send_default_pii=False,
        release=_package_version(),
    )
