"""Account settings email-change verification path."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from safeharbor.models import EmailChangeToken, User
from safeharbor.services.auth_service import hash_password


@pytest.fixture
def sent_emails(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    from safeharbor.blueprints.auth import email_change

    sent: list[dict[str, str]] = []

    def fake_send(*, to_email: str, new_email: str, token: str) -> None:
        sent.append({"to_email": to_email, "new_email": new_email, "token": token})

    monkeypatch.setattr(email_change, "_send_email_change_confirmation", fake_send)

    def fake_notify(*, to_email: str, new_email: str) -> None:
        sent.append({"to_email": to_email, "new_email": new_email, "kind": "applied"})

    monkeypatch.setattr(email_change, "_send_email_change_applied", fake_notify, raising=False)
    return sent


def _login(
    client, db_session, *, email: str = "old@example.com", password: str = "old-password-12345"
) -> User:
    user = User(email=email, password_hash=hash_password(password))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def test_account_get_requires_login(client, configured_user) -> None:
    resp = client.get("/settings/account", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_unauthenticated_redirects_to_login(client, configured_user) -> None:
    resp = client.post(
        "/settings/account/email",
        data={"new_email": "new@example.com", "current_password": "old-password-12345"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_account_get_renders_three_inline_forms(client, db_session) -> None:
    _login(client, db_session)

    resp = client.get("/settings/account")

    assert resp.status_code == 200
    assert b'action="/settings/account/email"' in resp.data
    assert b'action="/settings/account/password"' in resp.data
    assert b'action="/settings/account/display-name"' in resp.data
    assert b'name="new_email"' in resp.data
    assert b'name="new_password"' in resp.data
    assert b'name="username"' in resp.data


def test_nav_includes_display_and_system(client, db_session) -> None:
    _login(client, db_session)

    resp = client.get("/settings/account")

    assert resp.status_code == 200
    assert b'href="/settings/display"' in resp.data
    assert b">Display</a>" in resp.data
    assert b'href="/settings/account"' in resp.data
    assert b">Account</a>" in resp.data
    assert b'href="/settings/system"' in resp.data
    assert b">System</a>" in resp.data
    assert b">Password</a>" not in resp.data


def test_token_email_sent_to_new_address(client, db_session, sent_emails) -> None:
    user = _login(client, db_session)

    resp = client.post(
        "/settings/account/email",
        data={"new_email": "New@Example.COM ", "current_password": "old-password-12345"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db_session.refresh(user)
    assert user.email == "old@example.com"
    token = db_session.scalar(select(EmailChangeToken).where(EmailChangeToken.user_id == user.id))
    assert token is not None
    assert token.new_email == "new@example.com"
    assert sent_emails == [
        {
            "to_email": "new@example.com",
            "new_email": "new@example.com",
            "token": token.token,
        }
    ]


def test_duplicate_email_returns_form_error_no_500(client, db_session, sent_emails) -> None:
    user = _login(client, db_session)
    db_session.add(
        User(email="taken@example.com", password_hash=hash_password("old-password-12345"))
    )
    db_session.commit()

    resp = client.post(
        "/settings/account/email",
        data={"new_email": "taken@example.com", "current_password": "old-password-12345"},
    )

    assert resp.status_code == 200
    assert b"Email is already taken." in resp.data
    db_session.refresh(user)
    assert user.email == "old@example.com"
    token = db_session.scalar(select(EmailChangeToken).where(EmailChangeToken.user_id == user.id))
    assert token is None
    assert sent_emails == []


def test_verify_link_applies_email_and_notifies_old(client, db_session, sent_emails) -> None:
    user = _login(client, db_session)
    token = EmailChangeToken(
        token="valid-token",
        user_id=user.id,
        new_email="new@example.com",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
    )
    db_session.add(token)
    db_session.commit()

    resp = client.get(
        f"/settings/account/email/verify/{token.token}",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location == "/settings/account"
    db_session.refresh(user)
    db_session.refresh(token)
    assert user.email == "new@example.com"
    assert token.used_at is not None
    assert sent_emails == [
        {"to_email": "old@example.com", "new_email": "new@example.com", "kind": "applied"}
    ]


def test_verify_link_works_anonymously(client, db_session, sent_emails) -> None:
    user = User(email="old@example.com", password_hash=hash_password("old-password-12345"))
    db_session.add(user)
    db_session.flush()
    token = EmailChangeToken(
        token="anonymous-valid-token",
        user_id=user.id,
        new_email="new@example.com",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
    )
    db_session.add(token)
    db_session.commit()

    resp = client.get(
        f"/settings/account/email/verify/{token.token}",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location == "/settings/account"
    db_session.refresh(user)
    db_session.refresh(token)
    assert user.email == "new@example.com"
    assert token.used_at is not None
    assert sent_emails == [
        {"to_email": "old@example.com", "new_email": "new@example.com", "kind": "applied"}
    ]


def test_verify_link_applies_to_token_owner_not_clicker(client, db_session, sent_emails) -> None:
    owner = User(email="owner@example.com", password_hash=hash_password("owner-password-12345"))
    db_session.add(owner)
    db_session.flush()
    token = EmailChangeToken(
        token="wrong-session-valid-token",
        user_id=owner.id,
        new_email="owner-new@example.com",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
    )
    db_session.add(token)
    db_session.commit()
    clicker = _login(
        client,
        db_session,
        email="clicker@example.com",
        password="clicker-password-12345",
    )

    resp = client.get(
        f"/settings/account/email/verify/{token.token}",
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location == "/settings/account"
    db_session.refresh(owner)
    db_session.refresh(clicker)
    db_session.refresh(token)
    assert owner.email == "owner-new@example.com"
    assert clicker.email == "clicker@example.com"
    assert token.used_at is not None
    assert sent_emails == [
        {
            "to_email": "owner@example.com",
            "new_email": "owner-new@example.com",
            "kind": "applied",
        }
    ]


def test_verify_link_handles_duplicate_email_race(client, db_session, sent_emails) -> None:
    user = _login(client, db_session)
    token = EmailChangeToken(
        token="raced-token",
        user_id=user.id,
        new_email="new@example.com",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        created_at=datetime.now(UTC),
    )
    db_session.add(token)
    db_session.commit()
    db_session.add(User(email="new@example.com", password_hash=hash_password("competing-password")))
    db_session.commit()

    resp = client.get(f"/settings/account/email/verify/{token.token}")

    assert resp.status_code == 410
    assert b"This email confirmation link is invalid or expired." in resp.data
    db_session.refresh(user)
    db_session.refresh(token)
    assert user.email == "old@example.com"
    assert token.used_at is None
    assert db_session.scalar(select(User.id).where(User.email == "new@example.com")) != user.id
    assert sent_emails == []


def test_verify_link_410_when_token_invalid(client, db_session, sent_emails) -> None:
    user = _login(client, db_session)

    resp = client.get("/settings/account/email/verify/not-a-real-token")

    assert resp.status_code == 410
    assert b"This email confirmation link is invalid or expired." in resp.data
    assert b'href="/settings/account"' in resp.data
    db_session.refresh(user)
    assert user.email == "old@example.com"
    assert sent_emails == []


def test_verify_link_410_when_token_expired(client, db_session, sent_emails) -> None:
    user = _login(client, db_session)
    token = EmailChangeToken(
        token="expired-token",
        user_id=user.id,
        new_email="new@example.com",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(token)
    db_session.commit()

    resp = client.get(f"/settings/account/email/verify/{token.token}")

    assert resp.status_code == 410
    assert b"This email confirmation link is invalid or expired." in resp.data
    db_session.refresh(user)
    db_session.refresh(token)
    assert user.email == "old@example.com"
    assert token.used_at is None
    assert sent_emails == []


def test_verify_link_410_when_token_used(client, db_session, sent_emails) -> None:
    user = _login(client, db_session)
    used_at = datetime.now(UTC) - timedelta(minutes=1)
    token = EmailChangeToken(
        token="used-token",
        user_id=user.id,
        new_email="new@example.com",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
        used_at=used_at,
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )
    db_session.add(token)
    db_session.commit()

    resp = client.get(f"/settings/account/email/verify/{token.token}")

    assert resp.status_code == 410
    assert b"This email confirmation link is invalid or expired." in resp.data
    db_session.refresh(user)
    db_session.refresh(token)
    assert user.email == "old@example.com"
    assert token.used_at is not None
    assert token.used_at.replace(tzinfo=UTC) == used_at
    assert sent_emails == []
