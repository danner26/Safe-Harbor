"""Coming-soon blueprint for authenticated placeholder routes."""

from __future__ import annotations

from flask import Blueprint

coming_soon_bp = Blueprint("coming_soon", __name__, url_prefix="/coming-soon")

from safeharbor.blueprints.coming_soon import views  # noqa: E402,F401
