"""Auth blueprint — login, logout, password change, registration via invite token,
admin-issued password resets, plus superuser-only invite/user management views."""

from __future__ import annotations

from flask import Blueprint

auth_bp = Blueprint("auth", __name__, template_folder="../../templates")

# Importing the views modules registers route handlers on auth_bp.
from safeharbor.blueprints.auth import admin_views, views  # noqa: E402, F401

__all__ = ["auth_bp"]
