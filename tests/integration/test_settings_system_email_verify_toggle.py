"""System settings email verification toggle."""

from __future__ import annotations

from sqlalchemy import select

from safeharbor.models import SystemSetting, User
from safeharbor.services.auth_service import hash_password


def _login(client, db_session, *, is_superuser: bool) -> User:
    user = User(
        email=f"system-toggle-{is_superuser}@example.com",
        password_hash=hash_password("pw-12345"),
        is_superuser=is_superuser,
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def test_unauthenticated_redirects_to_login(client, configured_user) -> None:
    resp = client.post(
        "/settings/system/email-verify-toggle",
        data={"enabled": "y"},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_admin_sees_toggle_row(client, db_session) -> None:
    _login(client, db_session, is_superuser=True)

    resp = client.get("/settings/system")

    assert resp.status_code == 200
    assert b"Email change verification" in resp.data
    assert b'action="/settings/system/email-verify-toggle"' in resp.data


def test_non_admin_does_not_see_toggle_row(client, db_session) -> None:
    _login(client, db_session, is_superuser=False)

    resp = client.get("/settings/system")

    assert resp.status_code == 200
    assert b"Email change verification" not in resp.data
    assert b'action="/settings/system/email-verify-toggle"' not in resp.data


def test_non_admin_post_returns_403(client, db_session) -> None:
    _login(client, db_session, is_superuser=False)

    resp = client.post(
        "/settings/system/email-verify-toggle",
        data={"enabled": "y"},
        follow_redirects=False,
    )

    assert resp.status_code == 403


def test_admin_post_persists_setting(client, db_session) -> None:
    admin = _login(client, db_session, is_superuser=True)

    resp = client.post(
        "/settings/system/email-verify-toggle",
        data={},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location == "/settings/system"
    setting = db_session.scalar(
        select(SystemSetting).where(SystemSetting.key == "email_verify_on_change")
    )
    assert setting is not None
    assert setting.value == "false"
    assert setting.updated_by_user_id == admin.id
