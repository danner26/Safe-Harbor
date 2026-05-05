"""Integration tests for recent measurement table attribution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select


def _login(client: FlaskClient, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email="recent@example.com",
        username="recentkeeper",
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


def _seed_recent_measurement(app: Flask, db_session: Any, recorded_by_user_id: Any) -> None:
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    _seed_reference_data(app)
    tank = Tank(name="Recent Reef", water_type="salt", profile_key="reef_sw")
    db_session.add(tank)
    db_session.commit()

    temperature = db_session.scalar(select(ParameterType).where(ParameterType.key == "temperature"))
    assert temperature is not None
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=temperature,
        value=Decimal("30.0"),
        value_unit="degC",
        recorded_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=recorded_by_user_id,
        note=None,
    )
    db_session.commit()


def test_recent_table_shows_logged_by(client: FlaskClient, app: Flask, db_session: Any) -> None:
    user = _login(client, db_session)
    _seed_recent_measurement(app, db_session, user.id)

    response = client.get("/")
    body = response.data.decode()

    assert response.status_code == 200
    assert "<th>Logged by</th>" in body
    assert "recentkeeper" in body
    assert "Out of range" in body
