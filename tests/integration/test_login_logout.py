"""Login + logout integration tests."""

from __future__ import annotations

from flask.testing import FlaskClient


def _seed_user(db_session, email: str, password: str, is_active: bool = True) -> "User":  # noqa
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(email=email, password_hash=hash_password(password), is_active=is_active)
    db_session.add(u)
    db_session.commit()
    return u


def test_login_get_renders_form(client: FlaskClient, configured_user) -> None:
    resp = client.get("/login")
    assert resp.status_code == 200
    assert b"Sign in" in resp.data or b"Log in" in resp.data
    assert b'name="email"' in resp.data
    assert b'name="password"' in resp.data


def test_login_happy_path(client: FlaskClient, db_session) -> None:
    _seed_user(db_session, "happy@x.com", "correct horse battery")
    resp = client.post(
        "/login",
        data={"email": "happy@x.com", "password": "correct horse battery"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    # Redirects to / (no next= supplied)
    assert resp.location.endswith("/") or resp.location == "/"


def test_login_updates_last_login_at(client: FlaskClient, db_session) -> None:
    from datetime import UTC, datetime

    u = _seed_user(db_session, "lla@x.com", "correct horse battery")
    assert u.last_login_at is None

    client.post("/login", data={"email": "lla@x.com", "password": "correct horse battery"})

    db_session.refresh(u)
    assert u.last_login_at is not None
    assert (datetime.now(UTC) - u.last_login_at).total_seconds() < 5


def test_login_wrong_password_returns_form_with_error(client: FlaskClient, db_session) -> None:
    _seed_user(db_session, "wp@x.com", "correct")
    resp = client.post(
        "/login",
        data={"email": "wp@x.com", "password": "wrong"},
        follow_redirects=False,
    )
    # 200 because we re-render the form (not a redirect)
    assert resp.status_code == 200
    assert b"incorrect" in resp.data.lower() or b"invalid" in resp.data.lower()


def test_login_unknown_email_uses_same_generic_error(client: FlaskClient, configured_user) -> None:
    resp = client.post(
        "/login",
        data={"email": "ghost@x.com", "password": "anything"},
    )
    assert resp.status_code == 200
    assert b"incorrect" in resp.data.lower() or b"invalid" in resp.data.lower()


def test_login_inactive_user_rejected(client: FlaskClient, db_session) -> None:
    _seed_user(db_session, "inactive@x.com", "correct", is_active=False)
    resp = client.post(
        "/login",
        data={"email": "inactive@x.com", "password": "correct"},
    )
    assert resp.status_code == 200  # form re-rendered with error
    # We use the SAME generic error — never reveal that the account is inactive
    assert b"incorrect" in resp.data.lower() or b"invalid" in resp.data.lower()


def test_login_next_param_redirects_to_target(client: FlaskClient, db_session) -> None:
    _seed_user(db_session, "n@x.com", "correct horse battery")
    resp = client.post(
        "/login?next=/admin/invites",
        data={"email": "n@x.com", "password": "correct horse battery"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "/admin/invites" in resp.location


def test_login_next_param_rejects_offsite(client: FlaskClient, db_session) -> None:
    _seed_user(db_session, "o@x.com", "correct horse battery")
    resp = client.post(
        "/login?next=https://evil.example.com/steal",
        data={"email": "o@x.com", "password": "correct horse battery"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "evil.example.com" not in resp.location


def test_login_next_param_rejects_protocol_relative(client: FlaskClient, db_session) -> None:
    _seed_user(db_session, "p@x.com", "correct horse battery")
    resp = client.post(
        "/login?next=//evil.example.com/steal",
        data={"email": "p@x.com", "password": "correct horse battery"},
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "evil.example.com" not in resp.location


def test_logout_clears_session(client: FlaskClient, db_session) -> None:
    _seed_user(db_session, "lo@x.com", "correct horse battery")
    client.post("/login", data={"email": "lo@x.com", "password": "correct horse battery"})

    resp = client.post("/logout", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.location

    # Subsequent / now redirects to /login (anonymous again)
    resp2 = client.get("/", follow_redirects=False)
    assert resp2.status_code == 302
    assert "/login" in resp2.location
