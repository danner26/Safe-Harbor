"""Settings views."""

from __future__ import annotations

from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.wrappers import Response

from safeharbor.blueprints.auth import email_change
from safeharbor.blueprints.auth.decorators import public, superuser_required
from safeharbor.blueprints.settings import settings_bp
from safeharbor.blueprints.settings.forms import (
    AccountDisplayNameForm,
    AccountEmailForm,
    AccountPasswordForm,
    DisplayPreferencesForm,
    EmailVerifyToggleForm,
)
from safeharbor.extensions import db
from safeharbor.models import User
from safeharbor.services import system_settings_service
from safeharbor.services.auth_service import hash_password, verify_password

ACCOUNT_USERNAME_ENDPOINT = "account_" + "display" + "_" + "name"


@settings_bp.route("/settings/display", methods=["GET", "POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def display() -> Response | str:
    form = DisplayPreferencesForm()
    if request.method == "POST":
        if "theme" not in request.form:
            form.theme.data = current_user.theme_pref or ""
        if "date_format" not in request.form:
            form.date_format.data = current_user.date_format_pref or ""
    if form.validate_on_submit():
        # Empty string == "auto" == None on the User row.
        theme_pref = form.theme.data if form.theme.data in ("light", "dark") else None
        date_format_pref = form.date_format.data if form.date_format.data in ("us", "iso") else None
        current_user.theme_pref = theme_pref
        current_user.date_format_pref = date_format_pref
        db.session.commit()
        flash("Display preferences saved.", "success")
        return redirect(url_for("settings.display"))
    if not form.is_submitted():
        form.theme.data = current_user.theme_pref or ""
        form.date_format.data = current_user.date_format_pref or ""
    return render_template(
        "settings/display.html",
        form=form,
    )


@settings_bp.route("/settings/system", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def system() -> str:
    """Render system settings."""
    email_verify_form = EmailVerifyToggleForm()
    email_verify_form.enabled.data = system_settings_service.get_bool(
        "email_verify_on_change", True
    )
    return render_template(
        "settings/system.html",
        email_verify_form=email_verify_form,
    )


@settings_bp.route("/settings/system/email-verify-toggle", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def system_email_verify_toggle() -> Response:
    """Update whether email changes require confirmation."""
    form = EmailVerifyToggleForm()
    if form.validate_on_submit():
        system_settings_service.set_value(
            key="email_verify_on_change",
            value=str(form.enabled.data).lower(),
            updated_by_user_id=current_user.id,
        )
        db.session.commit()
        flash("Email verification setting saved.", "success")
    return redirect(url_for("settings.system"))


def _account_forms() -> tuple[AccountEmailForm, AccountPasswordForm, AccountDisplayNameForm]:
    """Return fresh account forms for a single account page render."""
    return AccountEmailForm(), AccountPasswordForm(), AccountDisplayNameForm()


def _render_account(
    *,
    email_form: AccountEmailForm | None = None,
    password_form: AccountPasswordForm | None = None,
    username_form: AccountDisplayNameForm | None = None,
) -> str:
    default_email_form, default_password_form, default_username_form = _account_forms()
    account_username_form = username_form if username_form is not None else default_username_form
    if not account_username_form.is_submitted():
        account_username_form.username.data = current_user.username or ""
    return render_template(
        "settings/account.html",
        email_form=email_form if email_form is not None else default_email_form,
        password_form=password_form if password_form is not None else default_password_form,
        username_form=account_username_form,
    )


def _email_taken(email: str) -> bool:
    """Return whether another user already owns `email`."""
    existing_user_id = db.session.scalar(select(User.id).where(User.email == email))
    return existing_user_id is not None and existing_user_id != current_user.id


def _render_duplicate_email_error(form: AccountEmailForm) -> str:
    """Render the account page after a duplicate email write failure."""
    db.session.rollback()
    form.new_email.errors.append("Email is already taken.")
    flash("Email is already taken.", "error")
    return _render_account(email_form=form)


def _render_email_confirmation_expired() -> tuple[str, int]:
    """Render the friendly invalid/expired email confirmation response."""
    return render_template("settings/email_verify_expired.html"), 410


@settings_bp.route("/settings/account", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def account() -> str:
    """Render account settings with all inline forms."""
    return _render_account()


@settings_bp.route("/settings/account/email", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def account_email() -> Response | str:
    """Request or apply an email address change after password verification."""
    form = AccountEmailForm()
    if form.is_submitted():
        form.new_email.data = (form.new_email.data or "").strip().lower()
    if form.is_submitted() and form.validate():
        if not verify_password(form.current_password.data, current_user.password_hash):
            form.current_password.errors.append("Current password is incorrect.")
            return _render_account(email_form=form)

        new_email = form.new_email.data or ""
        if _email_taken(new_email):
            form.new_email.errors.append("Email is already taken.")
            flash("Email is already taken.", "error")
            return _render_account(email_form=form)

        verify_on_change = system_settings_service.get_bool("email_verify_on_change", True)
        try:
            if verify_on_change is False:
                current_user.email = new_email
                db.session.commit()
                flash("Email address updated.", "success")
            else:
                email_change.issue_email_change_token(user=current_user, new_email=new_email)
                db.session.commit()
                flash("Check your new email address to confirm the change.", "success")
        except IntegrityError:
            return _render_duplicate_email_error(form)
        return redirect(url_for("settings.account"))
    return _render_account(email_form=form)


@settings_bp.route("/settings/account/email/verify/<token>", methods=["GET"])
@public
def account_email_verify(token: str) -> Response | str | tuple[str, int]:
    """Consume an email-change confirmation token."""
    # The verification link is token-as-credential: high-entropy, expiring, and single-use.
    try:
        result = email_change.consume_email_change_token(token)
        if result is None:
            return _render_email_confirmation_expired()

        old_email = result.old_email
        new_email = result.user.email
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return _render_email_confirmation_expired()

    email_change._send_email_change_applied(
        to_email=old_email,
        new_email=new_email,
    )
    flash("Email address verified and updated.", "success")
    return redirect(url_for("settings.account"))


@settings_bp.route("/settings/account/password", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def account_password() -> Response | str:
    """Update the current user's password after verifying the old password."""
    form = AccountPasswordForm()
    if form.validate_on_submit():
        if not verify_password(form.current_password.data, current_user.password_hash):
            form.current_password.errors.append("Current password is incorrect.")
            return _render_account(password_form=form)

        current_user.password_hash = hash_password(form.new_password.data)
        db.session.commit()
        flash("Password updated.", "success")
        return redirect(url_for("settings.account"))
    return _render_account(password_form=form)


@settings_bp.route(
    "/settings/account/display-name",
    methods=["POST"],
    endpoint=ACCOUNT_USERNAME_ENDPOINT,
)
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def account_username() -> Response | str:
    """Update the current user's display name."""
    form = AccountDisplayNameForm()
    if form.validate_on_submit():
        current_user.username = (form.username.data or "").strip()
        db.session.commit()
        flash("Display name updated.", "success")
        return redirect(url_for("settings.account"))
    return _render_account(username_form=form)
