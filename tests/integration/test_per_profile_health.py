"""Per-profile health integration coverage for dashboard rollups."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from flask import Flask
from flask.testing import FlaskClient
from sqlalchemy import select


def _login(client: FlaskClient, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email="per-profile-health@example.com",
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


def _parameter(db_session: Any, key: str) -> Any:
    from safeharbor.models.parameter_type import ParameterType

    parameter = db_session.scalar(select(ParameterType).where(ParameterType.key == key))
    assert parameter is not None
    return parameter


def _seed_tank_with_reading(
    app: Flask,
    db_session: Any,
    *,
    name: str,
    water_type: str,
    profile_key: str,
    parameter_key: str,
    value: Decimal,
    value_unit: str,
) -> Any:
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    _seed_reference_data(app)
    tank = Tank(name=name, water_type=water_type, profile_key=profile_key)
    db_session.add(tank)
    db_session.flush()
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=_parameter(db_session, parameter_key),
        value=value,
        value_unit=value_unit,
        recorded_at=datetime.now(UTC) - timedelta(days=1),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()
    return tank


def _tank_card(body: str, tank_name: str) -> str:
    name_index = body.index(tank_name)
    start = body.rindex('<article class="card"', 0, name_index)
    end = body.index("</article>", name_index)
    return body[start:end]


def test_goldfish_70f_rolls_up_healthy(
    client: FlaskClient,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_reading(
        app,
        db_session,
        name="Goldfish 70F",
        water_type="fresh",
        profile_key="coldwater_fw",
        parameter_key="temperature",
        value=Decimal("70.0"),
        value_unit="degF",
    )

    response = client.get("/")
    card = _tank_card(response.data.decode(), tank.name)

    assert response.status_code == 200
    assert "Nominal" in card


def test_tropical_70f_rolls_up_watch_or_action_needed(
    client: FlaskClient,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_reading(
        app,
        db_session,
        name="Tropical 70F",
        water_type="fresh",
        profile_key="tropical_fw_community",
        parameter_key="temperature",
        value=Decimal("70.0"),
        value_unit="degF",
    )

    response = client.get("/")
    card = _tank_card(response.data.decode(), tank.name)

    assert response.status_code == 200
    assert "Watch" in card or "Action needed" in card


def test_reef_phosphate_high_rolls_up_unhealthy(
    client: FlaskClient,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_reading(
        app,
        db_session,
        name="Reef Phosphate",
        water_type="salt",
        profile_key="reef_sw",
        parameter_key="phosphate",
        value=Decimal("0.5"),
        value_unit="ppm",
    )

    response = client.get("/")
    card = _tank_card(response.data.decode(), tank.name)

    assert response.status_code == 200
    assert "Action needed" in card


def test_fowlr_phosphate_same_rolls_up_healthy_or_watch(
    client: FlaskClient,
    app: Flask,
    db_session: Any,
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_reading(
        app,
        db_session,
        name="FOWLR Phosphate",
        water_type="salt",
        profile_key="fowlr_sw",
        parameter_key="phosphate",
        value=Decimal("0.5"),
        value_unit="ppm",
    )

    response = client.get("/")
    card = _tank_card(response.data.decode(), tank.name)

    assert response.status_code == 200
    assert "Action needed" not in card
    assert "Nominal" in card or "Watch" in card
