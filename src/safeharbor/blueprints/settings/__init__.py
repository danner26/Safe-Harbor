"""Settings blueprint — display preferences (units), additional sections in 1c.3."""

from __future__ import annotations

from flask import Blueprint

settings_bp = Blueprint("settings", __name__, template_folder="../../templates")

# Importing the views module registers route handlers on settings_bp.
from safeharbor.blueprints.settings import views  # noqa: E402, F401

__all__ = ["settings_bp"]
