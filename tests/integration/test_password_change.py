"""Authenticated user changing their own password."""

from __future__ import annotations


def _login_as(client, db_session, email: str, password: str):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(email=email, password_hash=hash_password(password))
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    return u


def test_settings_password_get_requires_login(client, configured_user) -> None:
    resp = client.get("/settings/password", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.location


def test_settings_password_get_renders_form(client, db_session) -> None:
    _login_as(client, db_session, "u@x.com", "current-pw-12345")
    resp = client.get("/settings/password")
    assert resp.status_code == 200
    assert b'name="current"' in resp.data
    assert b'name="password"' in resp.data
    assert b'name="confirm"' in resp.data


def test_settings_password_post_happy_path(client, db_session) -> None:
    from safeharbor.services.auth_service import verify_password

    u = _login_as(client, db_session, "h@x.com", "current-pw-12345")
    resp = client.post(
        "/settings/password",
        data={
            "current": "current-pw-12345",
            "password": "new-secret-12345",
            "confirm": "new-secret-12345",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (200, 302)
    db_session.refresh(u)
    assert verify_password("new-secret-12345", u.password_hash) is True
    assert verify_password("current-pw-12345", u.password_hash) is False


def test_settings_password_post_rejects_wrong_current(client, db_session) -> None:
    _login_as(client, db_session, "w@x.com", "current-pw-12345")
    resp = client.post(
        "/settings/password",
        data={"current": "WRONG", "password": "new-secret-12345", "confirm": "new-secret-12345"},
    )
    assert resp.status_code == 200
    assert b"current" in resp.data.lower() or b"incorrect" in resp.data.lower()


def test_settings_password_post_rejects_short_new(client, db_session) -> None:
    _login_as(client, db_session, "s@x.com", "current-pw-12345")
    resp = client.post(
        "/settings/password",
        data={"current": "current-pw-12345", "password": "x", "confirm": "x"},
    )
    assert resp.status_code == 200
    assert b"at least 10" in resp.data or b"too short" in resp.data.lower()
