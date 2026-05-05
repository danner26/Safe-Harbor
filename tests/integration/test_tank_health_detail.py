"""Tank detail health rollup and parameter breakdown rendering."""

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

    user = User(email="tank-health@example.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_reference_data(app: Flask) -> None:
    result = app.test_cli_runner().invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0


def _seed_tank(app: Flask, db_session: Any, *, timezone: str = "UTC") -> Any:
    from safeharbor.models.tank import Tank

    _seed_reference_data(app)
    tank = Tank(
        name="Health Reef",
        water_type="salt",
        profile_key="reef_sw",
        timezone=timezone,
    )
    db_session.add(tank)
    db_session.commit()
    return tank


def _parameter(db_session: Any, key: str) -> Any:
    from safeharbor.models.parameter_type import ParameterType

    parameter = db_session.scalar(select(ParameterType).where(ParameterType.key == key))
    assert parameter is not None
    return parameter


def _record_measurement(
    db_session: Any,
    tank: Any,
    *,
    key: str,
    value: Decimal,
    recorded_at: datetime,
) -> None:
    from safeharbor.services import measurement_service

    measurement_service.record_measurement(
        tank=tank,
        parameter_type=_parameter(db_session, key),
        value=value,
        value_unit="degC" if key == "temperature" else "",
        recorded_at=recorded_at,
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()


def _seed_unhealthy_temperature(app: Flask, db_session: Any, *, timezone: str = "UTC") -> Any:
    tank = _seed_tank(app, db_session, timezone=timezone)
    _record_measurement(
        db_session,
        tank,
        key="temperature",
        value=Decimal("30.0"),
        recorded_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    return tank


def test_detail_renders_health_badge(client: FlaskClient, app: Flask, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_unhealthy_temperature(app, db_session)

    response = client.get(f"/tanks/{tank.id}")
    body = response.data.decode()

    assert response.status_code == 200
    assert "Action needed" in body


def test_detail_renders_breakdown_details_element(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_unhealthy_temperature(app, db_session)

    response = client.get(f"/tanks/{tank.id}")
    body = response.data.decode()

    assert response.status_code == 200
    assert '<details class="health-details" style="margin-top: 8px;">' in body
    assert "Why this status?" in body


def test_breakdown_lists_each_parameter_band_and_latest_value(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_unhealthy_temperature(app, db_session)

    response = client.get(f"/tanks/{tank.id}")
    body = response.data.decode()

    assert response.status_code == 200
    assert "<strong>Temperature:</strong> unhealthy" in body
    assert "30.0000 degC" in body
    assert "<strong>pH:</strong> never" in body


def test_breakdown_renders_recorded_at_in_tank_tz(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_unhealthy_temperature(app, db_session, timezone="America/Los_Angeles")

    response = client.get(f"/tanks/{tank.id}")
    body = response.data.decode()

    assert response.status_code == 200
    assert "May 1, 5:00 AM" in body
