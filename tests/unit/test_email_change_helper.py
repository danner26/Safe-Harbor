"""Email-change token helper tests."""

from __future__ import annotations

import logging
from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from flask import Flask
from sqlalchemy import select

from safeharbor import create_app
from safeharbor.config import TestConfig
from safeharbor.extensions import db
from safeharbor.models import EmailChangeToken, User


@pytest.fixture
def app(monkeypatch: pytest.MonkeyPatch, tmp_path) -> Generator[Flask, None, None]:
    """Point app factory upload validation at a test-owned directory."""
    monkeypatch.setattr(TestConfig, "UPLOAD_DIR", str(tmp_path))
    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


@pytest.fixture
def user(db_session) -> User:
    account = User(email="old@example.com", password_hash="hash")
    db_session.add(account)
    db_session.commit()
    return account


@pytest.fixture
def sent_emails(monkeypatch: pytest.MonkeyPatch) -> Generator[list[dict[str, str]], None, None]:
    from safeharbor.blueprints.auth import email_change

    sent: list[dict[str, str]] = []

    def fake_send(*, to_email: str, new_email: str, token: str) -> None:
        sent.append({"to_email": to_email, "new_email": new_email, "token": token})

    monkeypatch.setattr(email_change, "_send_email_change_confirmation", fake_send)
    yield sent


def test_issue_token_creates_unused_row(app: Flask, db_session, user: User, sent_emails) -> None:
    from safeharbor.blueprints.auth.email_change import TOKEN_TTL, issue_email_change_token

    before = datetime.now(UTC)

    token_row = issue_email_change_token(user=user, new_email="new@example.com")

    assert token_row.id is not None
    assert token_row.user_id == user.id
    assert token_row.new_email == "new@example.com"
    assert token_row.used_at is None
    assert len(token_row.token) >= 32
    assert before + TOKEN_TTL - timedelta(seconds=2) <= token_row.expires_at
    assert token_row.expires_at <= before + TOKEN_TTL + timedelta(seconds=2)
    assert db_session.scalar(select(EmailChangeToken).where(EmailChangeToken.id == token_row.id))
    assert sent_emails == [
        {
            "to_email": "new@example.com",
            "new_email": "new@example.com",
            "token": token_row.token,
        }
    ]


def test_send_confirmation_log_does_not_include_token(
    app: Flask, caplog: pytest.LogCaptureFixture
) -> None:
    from safeharbor.blueprints.auth.email_change import _send_email_change_confirmation

    token = "secret-email-change-token"

    with caplog.at_level(logging.INFO, logger=app.logger.name):
        _send_email_change_confirmation(
            to_email="new@example.com", new_email="new@example.com", token=token
        )

    assert token not in caplog.text
    assert "new@example.com" in caplog.text


def test_consume_valid_token_applies_email(app: Flask, db_session, user: User, sent_emails) -> None:
    from safeharbor.blueprints.auth.email_change import (
        consume_email_change_token,
        issue_email_change_token,
    )

    token_row = issue_email_change_token(user=user, new_email="new@example.com")
    raw_token = token_row.token
    result = consume_email_change_token(raw_token)

    assert result is not None
    assert result.user == user
    assert result.old_email == "old@example.com"
    assert user.email == "new@example.com"
    assert token_row.used_at is not None


def test_consume_expired_token_returns_none(app: Flask, db_session, user: User) -> None:
    from safeharbor.blueprints.auth.email_change import consume_email_change_token

    token_row = EmailChangeToken(
        token="expired-token",
        user_id=user.id,
        new_email="new@example.com",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )
    db_session.add(token_row)
    db_session.commit()

    assert consume_email_change_token("expired-token") is None

    assert user.email == "old@example.com"
    assert token_row.used_at is None


def test_consume_used_token_returns_none(app: Flask, db_session, user: User) -> None:
    from safeharbor.blueprints.auth.email_change import consume_email_change_token

    token_row = EmailChangeToken(
        token="used-token",
        user_id=user.id,
        new_email="new@example.com",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db_session.add(token_row)
    db_session.commit()
    used_at = datetime.now(UTC)
    token_row.used_at = used_at
    db_session.commit()

    assert consume_email_change_token("used-token") is None

    assert user.email == "old@example.com"
    assert token_row.used_at == used_at


def test_consume_does_not_commit(
    app, db_session, user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    from safeharbor.blueprints.auth.email_change import (
        consume_email_change_token,
        issue_email_change_token,
    )

    token_row = issue_email_change_token(user=user, new_email="new@example.com")

    def fail_commit() -> None:
        raise AssertionError("consume_email_change_token must not commit")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    result = consume_email_change_token(token_row.token)

    assert result is not None
    assert result.user == user
    assert result.old_email == "old@example.com"
    assert user.email == "new@example.com"
