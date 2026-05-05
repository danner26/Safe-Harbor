"""Integration tests for authenticated navigation cleanup."""

from __future__ import annotations

import re
from typing import Any

from flask import url_for


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email="daniel.anner@danstechsupport.com",
        password_hash=hash_password("test-pw-12345"),
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _href_for_label(body: str, label: str) -> str:
    match = re.search(rf'<a\s+href="([^"]+)"[^>]*>\s*{re.escape(label)}\s*</a>', body)
    assert match is not None
    return match.group(1)


def test_login_page_does_not_render_nav_links(client: Any) -> None:
    resp = client.get("/login")

    assert resp.status_code == 200
    body = resp.data.decode()
    for label in ("Tanks", "Livestock", "Measurements", "Alerts", "Reports", "More"):
        assert f">{label}<" not in body


def test_authenticated_page_renders_nav_links(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get("/")

    assert resp.status_code == 200
    body = resp.data.decode()
    for label in ("Tanks", "Livestock", "Measurements", "Alerts", "Reports", "More"):
        assert f">{label}<" in body


def test_tanks_link_routes_to_real_route(client: Any, app: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get("/")

    assert resp.status_code == 200
    with app.test_request_context():
        assert _href_for_label(resp.data.decode(), "Tanks") == url_for("tanks.list_tanks")


def test_alerts_link_routes_to_coming_soon(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get("/")

    assert resp.status_code == 200
    assert _href_for_label(resp.data.decode(), "Alerts") == "/coming-soon/alerts"


def test_coming_soon_renders(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get("/coming-soon/alerts")

    assert resp.status_code == 200
    assert b"Alerts" in resp.data


def test_coming_soon_unauthenticated_redirects_to_login(client: Any) -> None:
    resp = client.get("/coming-soon/alerts", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location
