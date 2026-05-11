"""Setup blueprint views for first-run administrator bootstrap."""

from __future__ import annotations

from flask import abort, redirect, render_template, url_for
from sqlalchemy import select
from werkzeug.wrappers import Response

from safeharbor.blueprints.auth.decorators import public
from safeharbor.blueprints.setup import setup_bp
from safeharbor.blueprints.setup.forms import SetupForm
from safeharbor.extensions import db
from safeharbor.models.account import User
from safeharbor.services.auth_service import create_first_admin


@setup_bp.route("/setup", methods=["GET", "POST"])
@public
def show_or_create() -> Response | str:
    """Render setup form and create the first admin when no users exist."""
    if db.session.scalar(select(User).limit(1)) is not None:
        abort(404)

    form = SetupForm()
    if form.validate_on_submit():
        try:
            create_first_admin(
                email=form.email.data,
                password=form.password.data,
                preferred_units=form.preferred_units.data,
            )
        except ValueError:
            db.session.rollback()
            abort(404)
        db.session.commit()
        return redirect(url_for("auth.login"))

    return render_template("setup/setup.html", form=form)
