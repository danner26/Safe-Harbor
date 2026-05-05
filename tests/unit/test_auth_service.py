"""Unit tests for safeharbor.services.auth_service password helpers and token mint/verify."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from safeharbor.models.account import User
from safeharbor.models.invite import InviteKind
from safeharbor.services.auth_service import (
    InvalidTokenError,
    hash_password,
    issue_invite_token,
    redeem_token,
    verify_password,
)


def test_hash_password_returns_argon2_string() -> None:
    h = hash_password("correct horse battery staple")
    assert h.startswith("$argon2")
    assert len(h) > 50


def test_hash_password_is_not_deterministic() -> None:
    a = hash_password("same-pw")
    b = hash_password("same-pw")
    assert a != b  # salt differs


def test_verify_password_round_trip() -> None:
    h = hash_password("hunter2-is-not-a-good-password")
    assert verify_password("hunter2-is-not-a-good-password", h) is True


def test_verify_password_rejects_wrong() -> None:
    h = hash_password("right")
    assert verify_password("wrong", h) is False


def test_verify_password_handles_garbage_hash() -> None:
    assert verify_password("anything", "not-a-real-hash") is False


# ---------------------------------------------------------------------------
# Token mint / verify tests (Task 4)
# ---------------------------------------------------------------------------


def test_issue_invite_token_creates_row_and_returns_url_payload(app, db_session) -> None:
    issuer = User(email="admin@x.com", password_hash="h", is_superuser=True)
    db_session.add(issuer)
    db_session.commit()

    with app.app_context():
        token, invite = issue_invite_token(
            email="newbie@x.com",
            kind=InviteKind.INVITE,
            issued_by=issuer.id,
        )
    db_session.commit()

    # Token is non-empty and signed (contains a separator)
    assert isinstance(token, str) and len(token) > 20
    # DB row exists with hash of the token
    expected_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert invite.token_hash == expected_hash
    assert invite.kind == "invite"
    assert invite.email == "newbie@x.com"
    assert invite.consumed_at is None
    # Expiry ~7 days out
    delta = invite.expires_at - datetime.now(UTC)
    assert timedelta(days=6, hours=23) < delta < timedelta(days=7, minutes=1)


def test_issue_password_reset_token_uses_one_hour_expiry(app, db_session) -> None:
    issuer = User(email="admin2@x.com", password_hash="h", is_superuser=True)
    db_session.add(issuer)
    db_session.commit()

    with app.app_context():
        _, invite = issue_invite_token(
            email="user@x.com",
            kind=InviteKind.PASSWORD_RESET,
            issued_by=issuer.id,
        )
    db_session.commit()
    delta = invite.expires_at - datetime.now(UTC)
    assert timedelta(minutes=59) < delta < timedelta(minutes=61)


def test_redeem_token_happy_path_marks_consumed(app, db_session) -> None:
    issuer = User(email="admin3@x.com", password_hash="h", is_superuser=True)
    consumer = User(email="consumer3@x.com", password_hash="h", is_superuser=False)
    db_session.add(issuer)
    db_session.add(consumer)
    db_session.commit()

    with app.app_context():
        token, invite = issue_invite_token(
            email="z@x.com",
            kind=InviteKind.INVITE,
            issued_by=issuer.id,
        )
        db_session.commit()
        consumer_id = consumer.id
        redeemed = redeem_token(token, kind=InviteKind.INVITE, consumer_id=consumer_id)
    db_session.commit()

    assert redeemed.id == invite.id
    assert redeemed.consumed_at is not None
    assert redeemed.consumed_by == consumer_id


def test_redeem_token_rejects_tampered(app, db_session) -> None:
    issuer = User(email="admin4@x.com", password_hash="h", is_superuser=True)
    db_session.add(issuer)
    db_session.commit()

    with app.app_context():
        token, _ = issue_invite_token(
            email="t@x.com",
            kind=InviteKind.INVITE,
            issued_by=issuer.id,
        )
        db_session.commit()
        bad = token[:-3] + "AAA"
        with pytest.raises(InvalidTokenError):
            redeem_token(bad, kind=InviteKind.INVITE, consumer_id=uuid4())


def test_redeem_token_rejects_wrong_kind(app, db_session) -> None:
    issuer = User(email="admin5@x.com", password_hash="h", is_superuser=True)
    db_session.add(issuer)
    db_session.commit()

    with app.app_context():
        token, _ = issue_invite_token(
            email="k@x.com",
            kind=InviteKind.INVITE,
            issued_by=issuer.id,
        )
        db_session.commit()
        with pytest.raises(InvalidTokenError):
            redeem_token(token, kind=InviteKind.PASSWORD_RESET, consumer_id=uuid4())


def test_redeem_token_rejects_already_consumed(app, db_session) -> None:
    issuer = User(email="admin6@x.com", password_hash="h", is_superuser=True)
    consumer = User(email="consumer6@x.com", password_hash="h", is_superuser=False)
    db_session.add(issuer)
    db_session.add(consumer)
    db_session.commit()

    with app.app_context():
        token, _ = issue_invite_token(
            email="c@x.com",
            kind=InviteKind.INVITE,
            issued_by=issuer.id,
        )
        db_session.commit()
        redeem_token(token, kind=InviteKind.INVITE, consumer_id=consumer.id)
        db_session.commit()
        with pytest.raises(InvalidTokenError):
            redeem_token(token, kind=InviteKind.INVITE, consumer_id=consumer.id)


def test_redeem_token_rejects_expired(app, db_session, monkeypatch) -> None:
    issuer = User(email="admin7@x.com", password_hash="h", is_superuser=True)
    db_session.add(issuer)
    db_session.commit()

    with app.app_context():
        token, invite = issue_invite_token(
            email="e@x.com",
            kind=InviteKind.INVITE,
            issued_by=issuer.id,
        )
        # Force expiry into the past
        invite.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db_session.commit()
        with pytest.raises(InvalidTokenError):
            redeem_token(token, kind=InviteKind.INVITE, consumer_id=uuid4())
