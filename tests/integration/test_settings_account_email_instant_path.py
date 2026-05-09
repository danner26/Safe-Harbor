"""Account settings email-change immediate path."""

from __future__ import annotations

from safeharbor.models import SystemSetting, User
from safeharbor.services.auth_service import hash_password


def _login(client, db_session, *, password: str = "old-password-12345") -> User:
    user = User(email="old@example.com", password_hash=hash_password(password))
    db_session.add(user)
    db_session.add(SystemSetting(key="email_verify_on_change", value="false"))
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def test_unauthenticated_redirects_to_login(client, configured_user) -> None:
    resp = client.post(
        "/settings/account/email",
        data={"new_email": "new@example.com", "current_password": "old-password-12345"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_email_applies_immediately_when_toggle_off(client, db_session) -> None:
    user = _login(client, db_session)

    resp = client.post(
        "/settings/account/email",
        data={"new_email": "New@Example.COM ", "current_password": "old-password-12345"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db_session.refresh(user)
    assert user.email == "new@example.com"


def test_wrong_current_password_does_not_apply_instant_email(client, db_session) -> None:
    user = _login(client, db_session)

    resp = client.post(
        "/settings/account/email",
        data={"new_email": "new@example.com", "current_password": "wrong-password"},
    )

    assert resp.status_code == 200
    db_session.refresh(user)
    assert user.email == "old@example.com"
    assert b"Current password is incorrect" in resp.data


def test_duplicate_email_returns_form_error_no_500(client, db_session) -> None:
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
