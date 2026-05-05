"""Flask extension singletons.

Created uninitialized at module level; `create_app()` calls `init_app()` on each
to bind them to the application instance. This pattern keeps the app factory
clean and lets blueprints import these directly without circular imports."""

from __future__ import annotations

from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from redis import Redis
from rq import Queue

from safeharbor.models.base import Base

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
