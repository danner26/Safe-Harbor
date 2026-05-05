"""Login-required-by-default behavior — the before_request hook gate."""

from __future__ import annotations

from flask import Flask
from flask.testing import FlaskClient


def test_unauthenticated_root_redirects_to_login(client: FlaskClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.location


def test_unauthenticated_root_next_query_preserves_target(client: FlaskClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert "next=" in resp.location


def test_healthz_is_public(client: FlaskClient) -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200


def test_static_is_public(client: FlaskClient) -> None:
    # Even without auth, static files must remain reachable for the login
    # page to render with CSS.
    resp = client.get("/static/css/app.css")
    assert resp.status_code in (200, 404)  # 404 is fine if CSS isn't built; 401/302 is not


def test_authenticated_root_returns_200(app: Flask, client: FlaskClient, db_session) -> None:
    from safeharbor.models.account import User

    u = User(email="hh@x.com", password_hash="h", is_active=True)
    db_session.add(u)
    db_session.commit()

    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    resp = client.get("/")
    assert resp.status_code == 200
