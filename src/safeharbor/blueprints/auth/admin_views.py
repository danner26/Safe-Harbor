"""Auth blueprint — superuser-only management views."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from flask import flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required
from sqlalchemy import select
from werkzeug.wrappers import Response

from safeharbor.blueprints.auth import auth_bp
from safeharbor.blueprints.auth.decorators import superuser_required
from safeharbor.blueprints.auth.forms import IssueInviteForm
from safeharbor.extensions import db
from safeharbor.models.account import User
from safeharbor.models.invite import Invite, InviteKind
from safeharbor.services.auth_service import issue_invite_token

# Sessions store the just-issued raw token under this key, keyed by invite id,
# so the user sees it exactly once (after issue) and never on subsequent loads.
_PENDING_TOKEN_SESSION_KEY = "_auth_pending_invite_tokens"


def _stash_token(invite_id: UUID, token: str) -> None:
    pending: dict[str, str] = session.get(_PENDING_TOKEN_SESSION_KEY) or {}
    pending[str(invite_id)] = token
    session[_PENDING_TOKEN_SESSION_KEY] = pending


def _pop_token(invite_id: UUID) -> str | None:
    pending: dict[str, str] = session.get(_PENDING_TOKEN_SESSION_KEY) or {}
    token: str | None = pending.pop(str(invite_id), None)
    if pending:
        session[_PENDING_TOKEN_SESSION_KEY] = pending
    else:
        session.pop(_PENDING_TOKEN_SESSION_KEY, None)
    return token


@auth_bp.route("/admin/invites", methods=["GET", "POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_invites() -> Response | str:
    form = IssueInviteForm()
    if form.validate_on_submit():
        token, invite = issue_invite_token(
            email=form.email.data,
            kind=InviteKind.INVITE,
            issued_by=current_user.id,
        )
        db.session.commit()
        _stash_token(invite.id, token)
        return redirect(url_for("auth.admin_invite_detail", invite_id=invite.id))

    active = db.session.scalars(
        select(Invite)
        .where(Invite.kind == "invite", Invite.consumed_at.is_(None))
        .order_by(Invite.issued_at.desc())
    ).all()
    consumed = db.session.scalars(
        select(Invite)
        .where(Invite.kind == "invite", Invite.consumed_at.is_not(None))
        .order_by(Invite.issued_at.desc())
        .limit(20)
    ).all()
    now = datetime.now(UTC)
    return render_template(
        "auth/admin/invites_list.html",
        form=form,
        active=active,
        consumed=consumed,
        now=now,
    )


@auth_bp.route("/admin/invites/<uuid:invite_id>", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_invite_detail(invite_id: UUID) -> Response | str:
    invite = db.session.get(Invite, invite_id)
    if invite is None or invite.kind != "invite":
        flash("Invite not found.", "warning")
        return redirect(url_for("auth.admin_invites"))
    raw_token = _pop_token(invite_id)
    register_url = (
        url_for("auth.register_with_token", token=raw_token, _external=True) if raw_token else None
    )
    return render_template(
        "auth/admin/invite_detail.html",
        invite=invite,
        register_url=register_url,
        now=datetime.now(UTC),
    )


@auth_bp.route("/admin/invites/<uuid:invite_id>/revoke", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_invite_revoke(invite_id: UUID) -> Response:
    invite = db.session.get(Invite, invite_id)
    # kind check matches admin_invite_detail — POSTing a password-reset id
    # here would otherwise revoke the wrong row. Treat mismatch as not found.
    if invite is None or invite.kind != "invite":
        flash("Invite not found.", "warning")
        return redirect(url_for("auth.admin_invites"))
    if invite.consumed_at is not None:
        flash("Invite is already consumed or revoked.", "warning")
        return redirect(url_for("auth.admin_invites"))
    invite.consumed_at = datetime.now(UTC)
    invite.consumed_by = None  # revoked, not redeemed
    db.session.commit()
    flash("Invite revoked.", "success")
    return redirect(url_for("auth.admin_invites"))


# ---------- User management views ----------


@auth_bp.route("/admin/users", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_users() -> Response | str:
    users = db.session.scalars(select(User).order_by(User.created_at.desc())).all()
    return render_template("auth/admin/users_list.html", users=users)


@auth_bp.route("/admin/users/<uuid:user_id>", methods=["GET"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_user_detail(user_id: UUID) -> Response | str:
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "warning")
        return redirect(url_for("auth.admin_users"))
    last_reset_token = _pop_token(user.id)  # if just-issued, show the link once
    reset_url = (
        url_for("auth.password_reset_with_token", token=last_reset_token, _external=True)
        if last_reset_token
        else None
    )
    return render_template(
        "auth/admin/user_detail.html",
        user=user,
        reset_url=reset_url,
    )


@auth_bp.route("/admin/users/<uuid:user_id>/reset-password", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_user_reset_password(user_id: UUID) -> Response:
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "warning")
        return redirect(url_for("auth.admin_users"))
    token, _ = issue_invite_token(
        email=user.email,
        kind=InviteKind.PASSWORD_RESET,
        issued_by=current_user.id,
    )
    db.session.commit()
    _stash_token(user.id, token)
    return redirect(url_for("auth.admin_user_detail", user_id=user.id))


@auth_bp.route("/admin/users/<uuid:user_id>/deactivate", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_user_deactivate(user_id: UUID) -> Response:
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "warning")
        return redirect(url_for("auth.admin_users"))
    user.is_active = False
    db.session.commit()
    flash(f"Deactivated {user.email}.", "success")
    return redirect(url_for("auth.admin_user_detail", user_id=user.id))


@auth_bp.route("/admin/users/<uuid:user_id>/reactivate", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_user_reactivate(user_id: UUID) -> Response:
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "warning")
        return redirect(url_for("auth.admin_users"))
    user.is_active = True
    db.session.commit()
    flash(f"Reactivated {user.email}.", "success")
    return redirect(url_for("auth.admin_user_detail", user_id=user.id))


@auth_bp.route("/admin/users/<uuid:user_id>/promote", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_user_promote(user_id: UUID) -> Response:
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "warning")
        return redirect(url_for("auth.admin_users"))
    user.is_superuser = True
    db.session.commit()
    flash(f"Promoted {user.email} to superuser.", "success")
    return redirect(url_for("auth.admin_user_detail", user_id=user.id))


@auth_bp.route("/admin/users/<uuid:user_id>/demote", methods=["POST"])
@login_required  # type: ignore[misc, untyped-decorator, unused-ignore]
@superuser_required
def admin_user_demote(user_id: UUID) -> Response:
    user = db.session.get(User, user_id)
    if user is None:
        flash("User not found.", "warning")
        return redirect(url_for("auth.admin_users"))
    # Refuse to zero out the active superuser set
    other_supers = db.session.scalar(
        select(db.func.count(User.id)).where(
            User.is_superuser.is_(True), User.id != user.id, User.is_active.is_(True)
        )
    )
    if user.is_superuser and (other_supers or 0) == 0:
        flash("Cannot demote the last active superuser.", "danger")
        return redirect(url_for("auth.admin_user_detail", user_id=user.id))
    user.is_superuser = False
    db.session.commit()
    flash(f"Demoted {user.email}.", "success")
    return redirect(url_for("auth.admin_user_detail", user_id=user.id))
