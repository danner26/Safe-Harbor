"""Integration guards for removing the dashboard chart mock card."""

from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient


def _login(client: FlaskClient, db_session: Any) -> None:
    """Seed a user in the DB and inject a valid Flask-Login session."""
    from safeharbor.models.account import User

    user = User(email="dashboard-chart-removed@example.com", password_hash="h")
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def test_dashboard_does_not_render_hardcoded_chart_title(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)

    response = client.get("/")

    assert b"pH \xc2\xb7 Reef 90" not in response.data


def test_dashboard_does_not_render_chart_subtitle(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)

    response = client.get("/")

    assert b"Trailing seven days, smoothed" not in response.data


def test_dashboard_does_not_render_dashboard_chart_id(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)

    response = client.get("/")

    assert b'id="dashboard-chart"' not in response.data


def test_dashboard_recent_alerts_empty_state_still_renders(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)

    response = client.get("/")

    assert b"Alerts will appear here" in response.data
