"""Dashboard KPI strip + bottom-of-page Recent measurements table."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from flask import Flask
from flask.testing import FlaskClient


def _login(client: FlaskClient, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="d@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _login_with_units(client: FlaskClient, db_session: Any, units_pref: str | None) -> Any:
    user = _login(client, db_session)
    user.preferred_units = units_pref
    db_session.commit()
    return user


def _seed_app_state(app: Flask) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0


def test_dashboard_empty_state_for_zero_tanks_keeps_kpi_dashes(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    _login(client, db_session)
    _seed_app_state(app)

    resp = client.get("/")
    body = resp.data.decode()

    assert resp.status_code == 200
    assert "Add your first tank" in body
    assert body.count("&mdash;") >= 4


def test_dashboard_kpi_strip_uses_most_recent_tank_latest_per_parameter(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    from sqlalchemy import select

    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    _login_with_units(client, db_session, "imperial")
    _seed_app_state(app)

    older = Tank(name="Older", water_type="salt")
    newer = Tank(name="Newer", water_type="salt")
    db_session.add_all([older, newer])
    db_session.commit()

    temperature = db_session.scalar(select(ParameterType).where(ParameterType.key == "temperature"))
    assert temperature is not None
    now = datetime.now(UTC)
    measurement_service.record_measurement(
        tank=older,
        parameter_type=temperature,
        value=Decimal("99"),
        value_unit="degC",
        recorded_at=now - timedelta(hours=1),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    measurement_service.record_measurement(
        tank=newer,
        parameter_type=temperature,
        value=Decimal("25"),
        value_unit="degC",
        recorded_at=now,
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()

    resp = client.get("/")
    body = resp.data.decode()
    kpi_region = body.split("Your tanks", maxsplit=1)[0]

    assert resp.status_code == 200
    assert "77.0" in kpi_region
    assert "°F" in kpi_region
    assert "99.0000" not in kpi_region


def test_dashboard_recent_table_shows_across_tanks_with_readable_names(
    client: FlaskClient, app: Flask, db_session: Any
) -> None:
    from sqlalchemy import select

    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    _login(client, db_session)
    _seed_app_state(app)

    reef = Tank(name="Reef 90", water_type="salt")
    planted = Tank(name="Planted 40", water_type="fresh")
    db_session.add_all([reef, planted])
    db_session.commit()

    temperature = db_session.scalar(select(ParameterType).where(ParameterType.key == "temperature"))
    assert temperature is not None
    now = datetime.now(UTC)
    for tank, value, recorded_at in [
        (reef, "25", now),
        (planted, "22", now - timedelta(minutes=5)),
    ]:
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=temperature,
            value=Decimal(value),
            value_unit="degC",
            recorded_at=recorded_at,
            source="manual",
            recorded_by_user_id=None,
            note=None,
        )
    db_session.commit()

    resp = client.get("/")
    body = resp.data.decode()

    assert resp.status_code == 200
    assert "Reef 90" in body
    assert "Planted 40" in body
    assert "25.0000" in body
    assert "22.0000" in body
