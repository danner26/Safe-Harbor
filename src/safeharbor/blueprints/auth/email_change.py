"""Email-change token helpers."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from flask import current_app
from sqlalchemy import select

from safeharbor.extensions import db
from safeharbor.models import EmailChangeToken, User

TOKEN_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class EmailChangeResult:
    """Result returned after successfully consuming an email-change token."""

    user: User
    old_email: str


def _comparable_now(expires_at: datetime) -> datetime:
    """Return now with timezone shape matching the stored expiration."""
    now = datetime.now(UTC)
    if expires_at.tzinfo is None:
        return now.replace(tzinfo=None)
    return now


def issue_email_change_token(*, user: User, new_email: str) -> EmailChangeToken:
    """Create and send a single-use token for changing `user.email`.

    The caller owns the surrounding transaction and must commit it.
    """
    now = datetime.now(UTC)
    token = secrets.token_urlsafe(32)
    row = EmailChangeToken(
        token=token,
        user_id=user.id,
        new_email=new_email.strip().lower(),
        expires_at=now + TOKEN_TTL,
    )
    db.session.add(row)
    db.session.flush()
    _send_email_change_confirmation(to_email=row.new_email, new_email=row.new_email, token=token)
    return row


def consume_email_change_token(token: str) -> EmailChangeResult | None:
    """Apply an unused, unexpired email-change token and return the change result."""
    row = db.session.scalar(select(EmailChangeToken).where(EmailChangeToken.token == token))
    if row is None:
        return None
    now = _comparable_now(row.expires_at)
    if row.used_at is not None or row.expires_at <= now:
        return None

    user: User | None = db.session.get(User, row.user_id)
    if user is None:
        return None

    old_email = user.email
    user.email = row.new_email
    row.used_at = now
    db.session.flush()
    return EmailChangeResult(user=user, old_email=old_email)


def _send_email_change_confirmation(*, to_email: str, new_email: str, token: str) -> None:
    """Placeholder hook for sending an email-change confirmation."""
    _ = token
    current_app.logger.info(
        "Issued email-change confirmation for %s to confirm %s",
        to_email,
        new_email,
    )


def _send_email_change_applied(*, to_email: str, new_email: str) -> None:
    """Placeholder hook for notifying the old address after an email change."""
    current_app.logger.info(
        "Applied email-change confirmation for %s; notified previous address %s",
        new_email,
        to_email,
    )
