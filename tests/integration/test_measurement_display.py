"""Integration coverage for measurement value/unit display surfaces."""

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

    user = User(email="keeper@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_reference_data(app: Flask) -> None:
    result = app.test_cli_runner().invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0


def _seed_tank(db_session: Any, *, name: str = "Reef 90") -> Any:
    from safeharbor.models.tank import Tank

    tank = Tank(name=name, water_type="salt", timezone="UTC")
    db_session.add(tank)
    db_session.commit()
    return tank


def _temperature_parameter(db_session: Any) -> Any:
    from safeharbor.models.parameter_type import ParameterType

    parameter_type = db_session.scalar(
        select(ParameterType).where(ParameterType.key == "temperature")
    )
    assert parameter_type is not None
    return parameter_type


def _seed_temperature_measurement(
    app: Flask,
    db_session: Any,
    *,
    value: Decimal = Decimal("78"),
    value_unit: str = "degF",
) -> Any:
    from safeharbor.services import measurement_service

    _seed_reference_data(app)
    tank = _seed_tank(db_session)
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=_temperature_parameter(db_session),
        value=value,
        value_unit=value_unit,
        recorded_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note="display check",
    )
    db_session.commit()
    return measurement


def _assert_raw_temperature_display(body: str) -> None:
    assert "78.0000 °F" in body
    assert "25.5556 °C" not in body


def test_dashboard_recent_table_displays_raw_value_and_unit(
    client: FlaskClient,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    _seed_temperature_measurement(app, db_session)

    resp = client.get("/")

    assert resp.status_code == 200
    _assert_raw_temperature_display(resp.data.decode())


def test_tank_detail_recent_panel_displays_raw_value_and_unit(
    client: FlaskClient,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    measurement = _seed_temperature_measurement(app, db_session)

    resp = client.get(f"/tanks/{measurement.tank_id}")

    assert resp.status_code == 200
    _assert_raw_temperature_display(resp.data.decode())


def test_history_page_displays_raw_value_and_unit(
    client: FlaskClient,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    measurement = _seed_temperature_measurement(app, db_session)

    resp = client.get(f"/tanks/{measurement.tank_id}/history")

    assert resp.status_code == 200
    _assert_raw_temperature_display(resp.data.decode())


def test_measurement_display_falls_back_to_canonical_value_and_unit(
    client: FlaskClient,
    app: Flask,
    db_session: Any,
) -> None:
    from safeharbor.models.measurement import Measurement
    from safeharbor.models.unit import Unit

    _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session)
    raw_unit = db_session.scalar(select(Unit).where(Unit.code == "degF"))
    assert raw_unit is not None
    measurement = Measurement(
        tank_id=tank.id,
        parameter_type_id=_temperature_parameter(db_session).id,
        value=Decimal("25.0000"),
        recorded_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
        source="manual",
        raw_value=None,
        raw_unit_id=raw_unit.id,
        recorded_by_user_id=None,
        note="legacy canonical fallback check",
    )
    db_session.add(measurement)
    db_session.commit()

    resp = client.get(f"/tanks/{measurement.tank_id}/history")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "25.0000 °C" in body
    assert "°F" not in body
