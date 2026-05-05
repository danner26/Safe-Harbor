"""Integration guards for the dashboard alerts empty state."""

from __future__ import annotations

from typing import Any

from flask.testing import FlaskClient


def _login(client: FlaskClient, db_session: Any) -> None:
    """Seed a user in the DB and inject a valid Flask-Login session."""
    from safeharbor.models.account import User

    user = User(email="dashboard-alerts@example.com", password_hash="h")
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True


def test_dashboard_does_not_render_ph_drifting_mock(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)

    response = client.get("/")

    assert b"pH drifting low on Reef 90" not in response.data


def test_dashboard_does_not_render_backup_completed_mock(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)

    response = client.get("/")

    assert b"Backup completed" not in response.data


def test_dashboard_does_not_render_weekly_summary_mock(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)

    response = client.get("/")

    assert b"Weekly summary ready" not in response.data


def test_dashboard_does_not_render_nitrate_above_watch_mock(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)

    response = client.get("/")

    assert b"Nitrate above watch on Planted 40" not in response.data


def test_dashboard_renders_alerts_empty_state_text(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)

    response = client.get("/")

    assert b"Alerts will appear here when they're set up." in response.data
    assert b"(Phase 3)" in response.data
