"""System settings version row."""

from __future__ import annotations

from flask import Flask

from safeharbor.models import User
from safeharbor.services.auth_service import hash_password


def _login(client, db_session) -> User:
    user = User(email="system-version@example.com", password_hash=hash_password("pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def test_unauthenticated_redirects_to_login(client) -> None:
    resp = client.get("/settings/system", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_system_settings_renders_version_row(client, db_session, app: Flask) -> None:
    _login(client, db_session)
    app.jinja_env.globals["safeharbor_version"] = "9.8.7-test"

    resp = client.get("/settings/system")

    assert resp.status_code == 200
    assert b"Safe Harbor version" in resp.data
    assert b"9.8.7-test" in resp.data
