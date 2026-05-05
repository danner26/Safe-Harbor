"""Coming-soon routes for future Safe Harbor features."""

from __future__ import annotations

from flask import render_template
from flask_login import login_required  # type: ignore[import-untyped, unused-ignore]

from safeharbor.blueprints.coming_soon import coming_soon_bp


@coming_soon_bp.route("/<feature>", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def feature(feature: str) -> str:
    """Render a protected placeholder for a planned feature."""
    title = feature.replace("-", " ").replace("_", " ").title()
    description = f"{title} will land in a future phase. Track progress in the changelog."
    return render_template(
        "coming_soon/index.html",
        feature=feature,
        title=title,
        description=description,
    )
