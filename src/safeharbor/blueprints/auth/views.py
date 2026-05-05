"""Auth blueprint — public + authenticated views (admin views live in admin_views.py)."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from urllib.parse import urlparse

from flask import flash, redirect, render_template, request, url_for
from flask_login import login_required, login_user, logout_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.wrappers import Response

from safeharbor.blueprints.auth import auth_bp
from safeharbor.blueprints.auth.decorators import public
from safeharbor.blueprints.auth.forms import (
    ChangePasswordForm,
    LoginForm,
    PasswordResetForm,
    RegisterForm,
)
from safeharbor.extensions import db
from safeharbor.models.account import User
from safeharbor.models.invite import Invite, InviteKind
from safeharbor.services.auth_service import (
    InvalidTokenError,
    hash_password,
    install_preferred_units,
    redeem_token,
    verify_password,
)

GENERIC_LOGIN_ERROR = "Email or password is incorrect."
GENERIC_TOKEN_ERROR = "This invitation is invalid or expired."

# A real argon2id hash, computed once at import time. Used as the candidate hash
# when the submitted email doesn't exist, so verify_password runs the full
# argon2 work factor (~50ms) and timing doesn't leak email-existence.
# A literal placeholder string would be malformed, causing verify_password to
# raise+catch in ~0.05ms — defeating the timing-safety it's supposed to provide.
_DUMMY_PASSWORD_HASH = hash_password("__placeholder_for_timing_safety__")


def _safe_next(target: str | None) -> str:
    """Allow only same-origin, leading-slash next= targets.

    Rejects absolute URLs (scheme/netloc present), protocol-relative paths
    (starting with //), and backslash-prefixed paths (defense-in-depth against
    /\\evil.com style open-redirect payloads)."""
    if not target:
        return url_for("home.index")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        return url_for("home.index")
    if not target.startswith("/") or target.startswith("//"):
        return url_for("home.index")
    if "\\" in target:  # reject backslash-prefixed paths like /\evil.com
        return url_for("home.index")
    return target


@auth_bp.route("/login", methods=["GET", "POST"])
@public
def login() -> Response | str:
    """Render and handle the login form.

    On GET: render empty form.
    On POST with valid credentials: log the user in, update last_login_at,
    and redirect to next= (sanitised) or /. On any failure mode (wrong
    password, unknown email, inactive account) re-render the form with a
    single generic error message — no enumeration."""
    form = LoginForm()
    if form.validate_on_submit():
        # Normalize email casing/whitespace; users.email is stored lowercased
        # at registration time so case mismatches don't lock users out.
        normalized_email = (form.email.data or "").strip().lower()
        user = db.session.scalar(select(User).where(User.email == normalized_email))
        # Verify the password even if the user is missing, to avoid timing leaks
        # of email existence. verify_password swallows malformed-hash errors.
        candidate_hash = user.password_hash if user else _DUMMY_PASSWORD_HASH
        ok = verify_password(form.password.data, candidate_hash)
        if user is None or not ok or not user.is_active:
            flash(GENERIC_LOGIN_ERROR, "error")
            return render_template("auth/login.html", form=form)

        login_user(user, remember=form.remember.data)
        user.last_login_at = datetime.now(UTC)
        db.session.commit()
        return redirect(_safe_next(request.args.get("next")))
    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def logout() -> Response:
    """Log the current user out and redirect to the login page."""
    logout_user()
    return redirect(url_for("auth.login"))


# ---------------------------------------------------------------------------
# Register-with-token (Task 9)
# ---------------------------------------------------------------------------


def _peek_token_email(token: str, kind: InviteKind) -> str | None:
    """Best-effort lookup of the invite email for prefill, without consuming.

    Returns None if the token is invalid; the view then renders the error page."""
    from uuid import UUID

    from itsdangerous import BadSignature, SignatureExpired

    from safeharbor.services.auth_service import _KIND_TTL, _serializer

    ttl_seconds = int(_KIND_TTL[kind].total_seconds())
    try:
        invite_id_str = _serializer(kind).loads(token, max_age=ttl_seconds)
        invite_id = UUID(invite_id_str)
    except (BadSignature, SignatureExpired, ValueError):
        return None

    invite = db.session.get(Invite, invite_id)
    if invite is None or invite.kind != kind.value or invite.consumed_at is not None:
        return None
    if invite.expires_at <= datetime.now(UTC):
        return None
    if hashlib.sha256(token.encode("utf-8")).hexdigest() != invite.token_hash:
        return None
    return str(invite.email)


@auth_bp.route("/register/<token>", methods=["GET", "POST"])
@public
def register_with_token(token: str) -> Response | str | tuple[str, int]:
    """Public registration flow: validate invite token, create user, log in."""
    email = _peek_token_email(token, InviteKind.INVITE)
    if email is None:
        return render_template(
            "auth/register.html", form=None, email=None, error=GENERIC_TOKEN_ERROR
        ), 200

    form = RegisterForm()
    if form.validate_on_submit():
        # Re-check email isn't taken (race-safe in the same transaction as redeem)
        existing = db.session.scalar(select(User).where(User.email == email))
        if existing is not None:
            return render_template(
                "auth/register.html", form=None, email=None, error=GENERIC_TOKEN_ERROR
            ), 200
        try:
            new_user = User(
                email=email,
                username=form.username.data or None,
                password_hash=hash_password(form.password.data),
                is_active=True,
                is_superuser=False,
                preferred_units=install_preferred_units(),
            )
            db.session.add(new_user)
            db.session.flush()
            redeem_token(token, kind=InviteKind.INVITE, consumer_id=new_user.id)
            db.session.commit()
        except InvalidTokenError:
            db.session.rollback()
            return render_template(
                "auth/register.html", form=None, email=None, error=GENERIC_TOKEN_ERROR
            ), 200
        except IntegrityError:
            # Username collision or a race that created the email between the
            # pre-check and commit. Re-render with a field-level error so the
            # user can pick a different display name; same generic-error path
            # for email collisions to avoid enumeration.
            db.session.rollback()
            form.username.errors.append("That display name is already taken — pick another.")
            return render_template("auth/register.html", form=form, email=email, error=None), 200

        login_user(new_user)
        return redirect(url_for("home.index"))

    return render_template("auth/register.html", form=form, email=email, error=None)


# ---------------------------------------------------------------------------
# Password-reset-with-token (Task 10)
# ---------------------------------------------------------------------------


@auth_bp.route("/password-reset/<token>", methods=["GET", "POST"])
@public
def password_reset_with_token(token: str) -> Response | str | tuple[str, int]:
    """Public password-reset flow: validate reset token, update password, log in."""
    email = _peek_token_email(token, InviteKind.PASSWORD_RESET)
    if email is None:
        return render_template(
            "auth/password_reset.html", form=None, error=GENERIC_TOKEN_ERROR
        ), 200

    user = db.session.scalar(select(User).where(User.email == email))
    if user is None:
        return render_template(
            "auth/password_reset.html", form=None, error=GENERIC_TOKEN_ERROR
        ), 200

    form = PasswordResetForm()
    if form.validate_on_submit():
        try:
            user.password_hash = hash_password(form.password.data)
            redeem_token(token, kind=InviteKind.PASSWORD_RESET, consumer_id=user.id)
            db.session.commit()
        except InvalidTokenError:
            db.session.rollback()
            return render_template(
                "auth/password_reset.html", form=None, error=GENERIC_TOKEN_ERROR
            ), 200
        login_user(user)
        return redirect(url_for("home.index"))

    return render_template("auth/password_reset.html", form=form, error=None)


# ---------------------------------------------------------------------------
# Settings — change password (Task 11)
# ---------------------------------------------------------------------------


@auth_bp.route("/settings/password", methods=["GET", "POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
def settings_password() -> Response | str | tuple[str, int]:
    """Logged-in user changes their own password."""
    from flask_login import current_user

    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not verify_password(form.current.data, current_user.password_hash):
            form.current.errors.append("Current password is incorrect.")
            return render_template("auth/password_change.html", form=form), 200
        current_user.password_hash = hash_password(form.password.data)
        db.session.commit()
        flash("Password updated.", "success")
        return redirect(url_for("auth.settings_password"))
    return render_template("auth/password_change.html", form=form)
