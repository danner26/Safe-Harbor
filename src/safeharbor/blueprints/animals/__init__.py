"""Animals blueprint."""

from __future__ import annotations

from flask import Blueprint

animals_bp = Blueprint("animals", __name__, template_folder="../../templates")

from safeharbor.blueprints.animals import views  # noqa: E402, F401

__all__ = ["animals_bp"]
