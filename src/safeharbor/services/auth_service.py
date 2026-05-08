"""Authentication helpers — password hashing and token mint/verify."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID

from flask import current_app
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from passlib.exc import PasswordValueError, UnknownHashError
from passlib.hash import argon2
from sqlalchemy import func, select

from safeharbor.extensions import db
from safeharbor.models.account import User
from safeharbor.models.base import new_id
from safeharbor.models.invite import Invite, InviteKind

_FIRST_ADMIN_LOCK_KEY = 5_207_430_503_669_129_631


def hash_password(plaintext: str) -> str:
    """Return an argon2id hash of `plaintext` using passlib defaults.

    passlib's argon2.hash() includes a per-call random salt; two calls with
    the same plaintext produce different hashes."""
    return str(argon2.hash(plaintext))


def verify_password(plaintext: str, hashed: str) -> bool:
    """Return True iff `plaintext` matches `hashed`. False on any malformed input.

    Catches the narrow set of passlib exceptions that fire on garbage hashes,
    so callers can pass arbitrary DB-stored strings without wrapping in try/except."""
    try:
        return bool(argon2.verify(plaintext, hashed))
    except (UnknownHashError, PasswordValueError, ValueError):
        return False


def install_preferred_units() -> str:
    """Return the install-level preferred units value for new users."""
    preferred_units = db.session.scalar(
        select(User.preferred_units).where(User.preferred_units.is_not(None)).limit(1)
    )
    return preferred_units or "imperial"


def _lock_first_admin_creation() -> None:
    """Serialize first-admin creation on PostgreSQL for this transaction."""
    bind = db.session.get_bind()
    if bind.dialect.name != "postgresql":
        return
    db.session.execute(select(func.pg_advisory_xact_lock(_FIRST_ADMIN_LOCK_KEY)))


def create_first_admin(email: str, password: str, preferred_units: str) -> User:
    """Create the bootstrap superuser in the current transaction."""
    _lock_first_admin_creation()
    if db.session.scalar(select(User).limit(1)) is not None:
        raise ValueError("a user already exists")

    user = User(
        email=email.strip().lower(),
        password_hash=hash_password(password),
        is_active=True,
        is_superuser=True,
        preferred_units=preferred_units,
    )
    db.session.add(user)
    db.session.flush()
    return user


# ---------------------------------------------------------------------------
# Token mint / verify (Task 4)
# ---------------------------------------------------------------------------

# Token TTLs by kind. Authoritative copy lives on invites.expires_at; this
# only governs how long itsdangerous will accept its own signatures.
_KIND_TTL: dict[InviteKind, timedelta] = {
    InviteKind.INVITE: timedelta(days=7),
    InviteKind.PASSWORD_RESET: timedelta(hours=1),
}


class InvalidTokenError(Exception):
    """Raised by redeem_token() for any tamper/expiry/consumed/mismatch case.

    Callers should catch this and surface a single generic user-facing message
    ("This invitation is invalid or expired") to avoid leaking which condition
    failed."""


def _serializer(kind: InviteKind) -> URLSafeTimedSerializer:
    secret = current_app.config["SECRET_KEY"]
    return URLSafeTimedSerializer(secret, salt=str(kind.value))


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_invite_token(
    *,
    email: str,
    kind: InviteKind,
    issued_by: UUID,
) -> tuple[str, Invite]:
    """Create an Invite row and return (raw_token, invite).

    The caller is responsible for committing the surrounding transaction. The
    raw token is shown to the issuer ONCE (admin UI) and never persisted in
    plaintext — only its sha256 lives on invites.token_hash."""
    ttl = _KIND_TTL[kind]
    now = datetime.now(UTC)
    # Normalize email so admin-side typos like "Alice@X.COM" canonicalize to
    # "alice@x.com" — keeps invite list, password-reset target lookups, and
    # downstream User.email rows all on a consistent case.
    normalized_email = email.strip().lower()
    # Generate the id up front so we can sign the token and compute its hash
    # before INSERT — avoids a placeholder string in the UNIQUE token_hash
    # column, which would conflict if two invites were issued in one
    # transaction without an intervening commit.
    invite_id = new_id()
    token = _serializer(kind).dumps(str(invite_id))
    invite = Invite(
        id=invite_id,
        email=normalized_email,
        token_hash=_hash_token(token),
        kind=kind.value,
        issued_by=issued_by,
        expires_at=now + ttl,
    )
    db.session.add(invite)
    db.session.flush()
    return token, invite


def redeem_token(token: str, *, kind: InviteKind, consumer_id: UUID) -> Invite:
    """Validate `token` and mark its Invite row consumed in the current session.

    Raises InvalidTokenError on any failure mode: bad signature, wrong kind,
    expired (per itsdangerous OR per invites.expires_at), already-consumed,
    hash mismatch, or row not found. The caller commits."""
    ttl = _KIND_TTL[kind]
    try:
        invite_id_str = _serializer(kind).loads(token, max_age=int(ttl.total_seconds()))
    except (BadSignature, SignatureExpired) as exc:
        raise InvalidTokenError(str(exc)) from exc

    try:
        invite_id = UUID(invite_id_str)
    except ValueError as exc:
        raise InvalidTokenError("malformed payload") from exc

    invite: Invite | None = db.session.scalar(select(Invite).where(Invite.id == invite_id))
    if invite is None:
        raise InvalidTokenError("invite not found")
    if invite.kind != kind.value:
        raise InvalidTokenError("kind mismatch")
    if invite.consumed_at is not None:
        raise InvalidTokenError("already consumed")
    now = datetime.now(UTC)
    if invite.expires_at <= now:
        raise InvalidTokenError("expired")
    if invite.token_hash != _hash_token(token):
        raise InvalidTokenError("hash mismatch")

    invite.consumed_at = now
    invite.consumed_by = consumer_id
    return invite
