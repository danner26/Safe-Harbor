"""Integration tests for measurement history attribution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select


def _login(client: FlaskClient, db_session: Any, *, email: str, username: str | None) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email=email,
        username=username,
        password_hash=hash_password("test-pw-12345"),
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_reference_data(app: Flask) -> None:
    result = app.test_cli_runner().invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0


def _seed_measurement(app: Flask, db_session: Any, recorded_by_user_id: Any) -> Any:
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    _seed_reference_data(app)
    tank = Tank(name="Attribution Reef", water_type="salt")
    db_session.add(tank)
    db_session.commit()

    temperature = db_session.scalar(select(ParameterType).where(ParameterType.key == "temperature"))
    assert temperature is not None
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=temperature,
        value=Decimal("25.5"),
        value_unit="degC",
        recorded_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=recorded_by_user_id,
        note=None,
    )
    db_session.commit()
    return tank


def _history_row_for_temperature(body: str) -> str:
    tbody_at = body.index("<tbody>")
    marker_at = body.index("Temperature", tbody_at)
    start = body.rindex("<tr", 0, marker_at)
    end = body.index("</tr>", marker_at)
    return body[start:end]


def test_unauthenticated_redirects_to_login(client: FlaskClient, configured_user) -> None:
    response = client.get(f"/tanks/{uuid4()}/history", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.location


def test_logged_by_shows_username(client: FlaskClient, app: Flask, db_session: Any) -> None:
    user = _login(client, db_session, email="reefkeeper@example.com", username="reefkeeper")
    tank = _seed_measurement(app, db_session, user.id)

    response = client.get(f"/tanks/{tank.id}/history")
    body = response.data.decode()
    row = _history_row_for_temperature(body)

    assert response.status_code == 200
    assert "<th>Logged by</th>" in body
    assert "reefkeeper" in row


def test_logged_by_falls_back_to_email_prefix(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    user = _login(client, db_session, email="caretaker@example.com", username=None)
    tank = _seed_measurement(app, db_session, user.id)

    response = client.get(f"/tanks/{tank.id}/history")
    body = response.data.decode()
    row = _history_row_for_temperature(body)

    assert response.status_code == 200
    assert "caretaker" in row
    assert "caretaker@example.com" not in row
