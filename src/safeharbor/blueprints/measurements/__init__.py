"""Measurements blueprint - quick-add, batch entry, history, chart-data JSON."""

from __future__ import annotations

from flask import Blueprint

measurements_bp = Blueprint("measurements", __name__, template_folder="../../templates")

# Importing the views module registers route handlers on measurements_bp.
from safeharbor.blueprints.measurements import views  # noqa: E402, F401

__all__ = ["measurements_bp"]
