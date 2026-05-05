"""Tanks blueprint — CRUD, soft-decommission/restore, list/detail views."""

from __future__ import annotations

from flask import Blueprint

tanks_bp = Blueprint("tanks", __name__, template_folder="../../templates")

# Importing the views module registers route handlers on tanks_bp.
from safeharbor.blueprints.tanks import views  # noqa: E402, F401

__all__ = ["tanks_bp"]
