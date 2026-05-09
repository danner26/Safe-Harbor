"""Setup blueprint for first-run administrator bootstrap."""

from __future__ import annotations

from flask import Blueprint

setup_bp = Blueprint("setup", __name__, template_folder="../../templates")

# Importing the views module registers route handlers on setup_bp.
from safeharbor.blueprints.setup import views  # noqa: E402, F401

__all__ = ["setup_bp"]
