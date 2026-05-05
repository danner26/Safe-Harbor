"""Dashboard tank cards render computed health badges."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from flask.testing import FlaskClient

from safeharbor.models.account import User
from safeharbor.models.measurement import Measurement
from safeharbor.models.parameter_range import ParameterRange
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit
from safeharbor.services.auth_service import hash_password


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _login(client: FlaskClient, db_session: Any) -> User:
    user = User(
        email="tank-health-dashboard@example.com",
        password_hash=hash_password("test-pw-12345"),
    )
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_unit(db_session: Any) -> Unit:
    unit = Unit(code="ppm", display="ppm", dimension="concentration")
    db_session.add(unit)
    db_session.flush()
    return unit


def _seed_parameter(
    db_session: Any,
    unit: Unit,
    *,
    profile_key: str = "tropical_fw_community",
    min_value: Decimal = Decimal("0.0000"),
    max_value: Decimal = Decimal("10.0000"),
) -> ParameterType:
    parameter_type = ParameterType(
        key="temperature",
        display_name="Temperature",
        canonical_unit_id=unit.id,
        display_order=10,
    )
    db_session.add(parameter_type)
    db_session.flush()
    db_session.add(
        ParameterRange(
            parameter_type_id=parameter_type.id,
            water_type="fresh",
            profile_key=profile_key,
            min_value=min_value,
            max_value=max_value,
            stale_after_days=7,
            source="test",
        )
    )
    db_session.flush()
    return parameter_type


def _seed_parameter_range(
    db_session: Any,
    parameter_type: ParameterType,
    *,
    profile_key: str,
    min_value: Decimal,
    max_value: Decimal,
) -> None:
    db_session.add(
        ParameterRange(
            parameter_type_id=parameter_type.id,
            water_type="fresh",
            profile_key=profile_key,
            min_value=min_value,
            max_value=max_value,
            stale_after_days=7,
            source="test",
        )
    )
    db_session.flush()


def _seed_tank(
    db_session: Any,
    *,
    name: str = "Dashboard Tank",
    profile_key: str = "tropical_fw_community",
    created_at: datetime | None = None,
) -> Tank:
    tank = Tank(
        name=name,
        water_type="fresh",
        profile_key=profile_key,
        created_at=created_at or _now(),
        updated_at=created_at or _now(),
    )
    db_session.add(tank)
    db_session.flush()
    return tank


def _seed_measurement(
    db_session: Any,
    tank: Tank,
    parameter_type: ParameterType,
    *,
    value: Decimal,
) -> Measurement:
    measurement = Measurement(
        tank_id=tank.id,
        parameter_type_id=parameter_type.id,
        value=value,
        recorded_at=_now(),
        source="manual",
    )
    db_session.add(measurement)
    db_session.flush()
    return measurement


def _seed_health_reference(db_session: Any) -> ParameterType:
    unit = _seed_unit(db_session)
    return _seed_parameter(db_session, unit)


def _tank_card(body: str, tank_name: str) -> str:
    name_index = body.index(tank_name)
    start = body.rindex('<article class="card"', 0, name_index)
    end = body.index("</article>", name_index)
    return body[start:end]


def test_dashboard_renders_health_badge_per_tank(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    _seed_health_reference(db_session)
    _seed_tank(db_session, name="Desk 10")
    _seed_tank(db_session, name="Office 20")
    db_session.commit()

    response = client.get("/")
    body = response.data.decode()

    assert response.status_code == 200
    assert 'class="badge badge-success"' in _tank_card(body, "Desk 10")
    assert 'class="badge badge-success"' in _tank_card(body, "Office 20")


def test_unhealthy_reading_drives_action_needed_badge(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    parameter_type = _seed_health_reference(db_session)
    tank = _seed_tank(db_session)
    _seed_measurement(db_session, tank, parameter_type, value=Decimal("11.0000"))
    db_session.commit()

    response = client.get("/")
    card = _tank_card(response.data.decode(), tank.name)

    assert response.status_code == 200
    assert "Action needed" in card
    assert 'title="Temperature: unhealthy"' in card


def test_caution_reading_drives_watch_badge(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    parameter_type = _seed_health_reference(db_session)
    tank = _seed_tank(db_session)
    _seed_measurement(db_session, tank, parameter_type, value=Decimal("9.5000"))
    db_session.commit()

    response = client.get("/")
    card = _tank_card(response.data.decode(), tank.name)

    assert response.status_code == 200
    assert "Watch" in card
    assert 'title="Temperature: watch"' in card


def test_dashboard_renders_profile_specific_health_badges(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)
    unit = _seed_unit(db_session)
    parameter_type = _seed_parameter(
        db_session,
        unit,
        profile_key="tropical_fw_community",
        min_value=Decimal("21.0000"),
        max_value=Decimal("28.0000"),
    )
    _seed_parameter_range(
        db_session,
        parameter_type,
        profile_key="coldwater_fw",
        min_value=Decimal("18.3000"),
        max_value=Decimal("22.2000"),
    )
    tropical_tank = _seed_tank(
        db_session,
        name="Tropical Desk",
        profile_key="tropical_fw_community",
    )
    coldwater_tank = _seed_tank(
        db_session,
        name="Coldwater Desk",
        profile_key="coldwater_fw",
    )
    _seed_measurement(db_session, tropical_tank, parameter_type, value=Decimal("21.1000"))
    _seed_measurement(db_session, coldwater_tank, parameter_type, value=Decimal("21.1000"))
    db_session.commit()

    response = client.get("/")
    body = response.data.decode()

    assert response.status_code == 200
    assert "Watch" in _tank_card(body, "Tropical Desk")
    assert 'title="Temperature: watch"' in _tank_card(body, "Tropical Desk")
    assert "Nominal" in _tank_card(body, "Coldwater Desk")
    assert 'title="Temperature: healthy"' in _tank_card(body, "Coldwater Desk")


def test_no_measurements_recent_tank_shows_nominal(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    _seed_health_reference(db_session)
    tank = _seed_tank(db_session)
    db_session.commit()

    response = client.get("/")
    card = _tank_card(response.data.decode(), tank.name)

    assert response.status_code == 200
    assert "Nominal" in card
    assert 'title="Temperature: never"' in card


def test_brand_new_tank_with_old_created_at_shows_unknown(
    client: FlaskClient, db_session: Any
) -> None:
    _login(client, db_session)
    _seed_health_reference(db_session)
    tank = _seed_tank(db_session, created_at=_now() - timedelta(days=10))
    db_session.commit()

    response = client.get("/")
    card = _tank_card(response.data.decode(), tank.name)

    assert response.status_code == 200
    assert "Unknown" in card
    assert 'title="Temperature: never"' in card
