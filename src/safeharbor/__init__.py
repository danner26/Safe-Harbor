"""Safe Harbor application factory.

Usage:
    from safeharbor import create_app
    app = create_app("production")
"""

from __future__ import annotations

import importlib.metadata
import logging
import os
import secrets
from pathlib import Path

from flask import Flask
from redis import Redis
from rq import Queue
from werkzeug.middleware.proxy_fix import ProxyFix

from safeharbor import extensions
from safeharbor.cli import register_cli
from safeharbor.config import ProdConfig, get_config

_SAFEHARBOR_VERSION_FALLBACK = "0.1.0"


def create_app(config_name: str | None = None) -> Flask:
    """Build and return a configured Flask application instance."""
    resolved: str = (
        config_name if config_name is not None else (os.getenv("FLASK_CONFIG") or "development")
    )
    config_cls = get_config(resolved)

    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_cls)

    if config_cls is ProdConfig:
        ProdConfig.validate()

    _validate_upload_dir(app)
    _configure_logging(app)
    _configure_visual_admin_password(app)
    _init_extensions(app)
    _wire_proxy_fix(app)
    _register_blueprints(app)
    _register_template_globals(app)
    register_cli(app)

    return app


def _validate_upload_dir(app: Flask) -> None:
    upload_dir = Path(app.config["UPLOAD_DIR"])
    if not upload_dir.exists():
        raise RuntimeError(
            f"UPLOAD_DIR does not exist: {upload_dir}. Create the directory and ensure "
            "the app process can write to it."
        )
    if not upload_dir.is_dir():
        raise RuntimeError(
            f"UPLOAD_DIR is not a directory: {upload_dir}. Point UPLOAD_DIR at a writable "
            "directory."
        )
    if not os.access(upload_dir, os.W_OK):
        raise RuntimeError(
            f"UPLOAD_DIR is not writable: {upload_dir}. Ensure the app process can write "
            "to this directory."
        )


def _package_version() -> str:
    try:
        return importlib.metadata.version("safeharbor")
    except importlib.metadata.PackageNotFoundError:
        return _SAFEHARBOR_VERSION_FALLBACK


def _configure_logging(app: Flask) -> None:
    import uuid

    from flask import g, has_request_context, request

    level = getattr(logging, app.config["LOG_LEVEL"].upper(), logging.INFO)

    class RequestIdFilter(logging.Filter):
        def filter(self, record: logging.LogRecord) -> bool:
            if has_request_context():
                record.request_id = getattr(g, "request_id", "-")
            else:
                record.request_id = "-"
            return True

    handler = logging.StreamHandler()
    handler.setLevel(level)
    handler.addFilter(RequestIdFilter())
    if not app.debug and not app.testing:
        from pythonjsonlogger.json import JsonFormatter as _JsonFormatter

        handler.setFormatter(
            _JsonFormatter("%(asctime)s %(levelname)s %(name)s %(request_id)s %(message)s")
        )
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s")
        )
    app.logger.handlers = [handler]
    app.logger.setLevel(level)

    @app.before_request
    def _assign_request_id() -> None:
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:12]

    @app.after_request
    def _echo_request_id(response):  # type: ignore[no-untyped-def]
        if hasattr(g, "request_id"):
            response.headers["X-Request-Id"] = g.request_id
        return response


def _configure_visual_admin_password(app: Flask) -> None:
    """Generate a per-app visual fixture password when dev routes are enabled."""
    if not app.config["ENABLE_DEV_ROUTES"]:
        return
    env_password = os.getenv("DEV_VISUAL_ADMIN_PASSWORD", "")
    if env_password:
        app.config["DEV_VISUAL_ADMIN_PASSWORD"] = env_password
        return
    if app.config["DEV_VISUAL_ADMIN_PASSWORD"]:
        return
    token = secrets.token_urlsafe(24)
    app.config["DEV_VISUAL_ADMIN_PASSWORD"] = token
    app.logger.info("Generated DEV_VISUAL_ADMIN_PASSWORD for this app start")


def _init_extensions(app: Flask) -> None:
    extensions.db.init_app(app)
    extensions.migrate.init_app(app, extensions.db)
    extensions.login_manager.init_app(app)
    extensions.csrf.init_app(app)

    @extensions.login_manager.user_loader  # type: ignore
    def _load_user(user_id: str) -> User | None:  # type: ignore[name-defined]  # noqa: F821
        from uuid import UUID

        from safeharbor.models.account import User

        try:
            uid = UUID(user_id)
        except ValueError:
            return None
        return extensions.db.session.get(User, uid)

    # Import models here so SQLAlchemy's metadata is populated before any
    # create_all() / migrate call.  Noqa: F401 — imported for side-effect.
    import safeharbor.models  # noqa: F401

    extensions.redis_conn = Redis.from_url(app.config["REDIS_URL"])
    extensions.default_queue = Queue(connection=extensions.redis_conn)


def _wire_proxy_fix(app: Flask) -> None:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=0)  # type: ignore[method-assign]


def _register_template_globals(app: Flask) -> None:
    """Expose helper functions to Jinja templates as globals."""
    from flask import request
    from flask_login import current_user

    from safeharbor.utils.dates import format_recorded_at
    from safeharbor.utils.markdown import render_markdown
    from safeharbor.utils.units import liters_to_display

    def display_volume(liters):  # type: ignore[no-untyped-def]
        """Convert canonical liters to (value, unit) using the current user's pref + locale."""
        pref = (
            getattr(current_user, "preferred_units", None)
            if current_user.is_authenticated
            else None
        )
        accept_language = request.headers.get("Accept-Language") if request else None
        return liters_to_display(liters, pref, accept_language)

    app.jinja_env.globals["display_volume"] = display_volume
    app.jinja_env.globals["safeharbor_version"] = _package_version()
    app.jinja_env.filters["markdown"] = render_markdown
    app.jinja_env.filters["tank_local"] = lambda dt, tank, fmt="default": format_recorded_at(
        dt, tank, fmt=fmt
    )


def _register_blueprints(app: Flask) -> None:
    from safeharbor.blueprints.animals import animals_bp
    from safeharbor.blueprints.auth import auth_bp
    from safeharbor.blueprints.coming_soon import coming_soon_bp
    from safeharbor.blueprints.dev import dev_bp
    from safeharbor.blueprints.health import health_bp
    from safeharbor.blueprints.home import home_bp
    from safeharbor.blueprints.measurements import measurements_bp
    from safeharbor.blueprints.settings import settings_bp
    from safeharbor.blueprints.tanks import tanks_bp

    app.register_blueprint(home_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(animals_bp)
    app.register_blueprint(tanks_bp)
    app.register_blueprint(measurements_bp)
    app.register_blueprint(coming_soon_bp)
    app.register_blueprint(settings_bp)
    if app.config["ENABLE_DEV_ROUTES"]:
        app.register_blueprint(dev_bp)
    _install_login_required_hook(app)


def _install_login_required_hook(app: Flask) -> None:
    """Redirect anonymous requests to /login except for views marked @public."""
    from urllib.parse import urlparse

    from flask import redirect, request, url_for
    from flask_login import current_user

    @app.before_request
    def _require_login():  # type: ignore[no-untyped-def]
        if request.endpoint is None:
            return None
        if request.endpoint.startswith("static") or request.endpoint == "static":
            return None
        view = app.view_functions.get(request.endpoint)
        if view is not None and getattr(view, "_is_public", False):
            return None
        if current_user.is_authenticated:
            return None
        # Build a same-origin next= target. request.full_path keeps query string.
        target = request.full_path if request.full_path != "/?" else "/"
        # Defense: only allow same-origin redirects.
        parsed = urlparse(target)
        if parsed.scheme or parsed.netloc:
            target = "/"
        return redirect(url_for("auth.login", next=target))
