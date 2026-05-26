"""`/more` mobile overflow hub: lists destinations not in the bottom tab bar."""

from __future__ import annotations

from flask import Blueprint, render_template
from flask_login import login_required

more_bp = Blueprint("more", __name__, url_prefix="/more")


@more_bp.route("/", methods=["GET"], endpoint="index", strict_slashes=False)
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def index() -> str:
    return render_template("more/index.html")
