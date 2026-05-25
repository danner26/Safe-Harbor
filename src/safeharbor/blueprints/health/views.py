"""Health-check endpoints."""

from __future__ import annotations

import os

from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from safeharbor import extensions
from safeharbor.blueprints.auth.decorators import public
from safeharbor.extensions import db

health_bp = Blueprint("health", __name__)


@health_bp.route("/healthz")
@public
def healthz():  # type: ignore[no-untyped-def]
    """Return health status of app + dependencies."""
    db_status = _check_db()
    redis_status = _check_redis()
    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"
    email_status = "configured" if os.getenv("SMTP_HOST") else "disabled"
    payload = {
        "status": overall,
        "db": db_status,
        "redis": redis_status,
        "email": email_status,
    }
    code = 200 if overall == "ok" else 503
    return jsonify(payload), code


def _check_db() -> str:
    try:
        db.session.execute(text("SELECT 1"))
        return "ok"
    except Exception as exc:
        current_app.logger.warning("db healthcheck failed: %s", exc)
        return "down"


def _check_redis() -> str:
    # Late-bound module reference: extensions.redis_conn is reassigned in
    # create_app()._init_extensions(); a direct `from extensions import redis_conn`
    # would freeze the None at import time and never see the real connection.
    redis_conn = extensions.redis_conn
    if redis_conn is None:
        return "down"
    try:
        redis_conn.ping()
        return "ok"
    except Exception as exc:
        current_app.logger.warning("redis healthcheck failed: %s", exc)
        return "down"
