"""Integration tests for the More hub."""

from __future__ import annotations

from typing import Any

from flask import url_for


def _seed_user(db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email="daniel.anner@danstechsupport.com",
        password_hash=hash_password("test-pw-12345"),
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client: Any, user: Any) -> None:
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def test_more_hub_requires_login(client: Any, configured_user: Any) -> None:
    response = client.get("/more", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.location


def test_more_hub_renders_with_all_four_entries(client: Any, app: Any, db_session: Any) -> None:
    user = _seed_user(db_session)
    _login(client, user)

    response = client.get("/more")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    hub_start = body.index("data-more-hub")
    hub_body = body[hub_start : body.index("</nav>", hub_start)]
    with app.app_context():
        expected = [
            url_for("animals.list_animals"),
            url_for("measurements.index"),
            url_for("settings.display"),
            url_for("coming_soon.feature", feature="reports"),
        ]
        alerts_href = url_for("coming_soon.feature", feature="alerts")
    for href in expected:
        assert href in hub_body, f"missing {href} in /more body"
    # Alerts stays on the tab bar, NOT in the hub
    assert alerts_href not in hub_body
