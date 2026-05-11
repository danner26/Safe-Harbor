"""Account settings password form."""

from __future__ import annotations

from safeharbor.models import User
from safeharbor.services.auth_service import hash_password, verify_password


def _login(client, db_session, *, password: str = "old-password-12345") -> User:
    user = User(email="password@example.com", password_hash=hash_password(password))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def test_unauthenticated_redirects_to_login(client, configured_user) -> None:
    resp = client.post(
        "/settings/account/password",
        data={
            "current_password": "old-password-12345",
            "new_password": "new-password-12345",
            "confirm_password": "new-password-12345",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_password_updates_after_current_password_check(client, db_session) -> None:
    user = _login(client, db_session)

    resp = client.post(
        "/settings/account/password",
        data={
            "current_password": "old-password-12345",
            "new_password": "new-password-12345",
            "confirm_password": "new-password-12345",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db_session.refresh(user)
    assert verify_password("new-password-12345", user.password_hash) is True
    assert verify_password("old-password-12345", user.password_hash) is False


def test_wrong_current_password_rejects(client, db_session) -> None:
    user = _login(client, db_session)

    resp = client.post(
        "/settings/account/password",
        data={
            "current_password": "wrong-password",
            "new_password": "new-password-12345",
            "confirm_password": "new-password-12345",
        },
    )

    assert resp.status_code == 200
    db_session.refresh(user)
    assert verify_password("old-password-12345", user.password_hash) is True
    assert b"Current password is incorrect" in resp.data
