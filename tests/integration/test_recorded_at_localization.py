"""Integration coverage for tank-local measurement form timestamps."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import uuid4

from flask import Flask
from sqlalchemy import select


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(
        email=f"keeper-{uuid4()}@x.com",
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


def _seed_tank(
    db_session: Any,
    *,
    name: str = "Reef 90",
    water_type: str = "salt",
    timezone: str = "UTC",
) -> Any:
    from safeharbor.models.tank import Tank

    tank = Tank(name=name, water_type=water_type, timezone=timezone)
    db_session.add(tank)
    db_session.commit()
    return tank


def _quick_add_payload(tank_id: object, recorded_at: str) -> dict[str, str]:
    return {
        "tank_id": str(tank_id),
        "parameter_key": "temperature",
        "value": "78",
        "value_unit": "degF",
        "recorded_at": recorded_at,
        "note": "localized",
    }


def _record_quick_add(
    client: Any,
    db_session: Any,
    tank: Any,
    recorded_at: str,
) -> Any:
    from safeharbor.models.measurement import Measurement

    resp = client.post(
        "/measurements/quick-add",
        data=_quick_add_payload(tank.id, recorded_at),
        follow_redirects=False,
    )

    assert resp.status_code == 302
    rows = db_session.scalars(select(Measurement)).all()
    assert len(rows) == 1
    return rows[0]


def _seed_measurement(app: Flask, db_session: Any, tank: Any) -> Any:
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.services import measurement_service

    parameter_type = db_session.scalar(
        select(ParameterType).where(ParameterType.key == "temperature")
    )
    assert parameter_type is not None
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("78"),
        value_unit="degF",
        recorded_at=datetime(2026, 4, 30, 13, 45, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note="before",
    )
    db_session.commit()
    return measurement


def test_quick_add_in_est_tank_stores_utc_offset(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session, timezone="America/New_York")

    measurement = _record_quick_add(client, db_session, tank, "2026-01-15T14:00")

    assert measurement.recorded_at == datetime(2026, 1, 15, 19, 0, tzinfo=UTC)


def test_quick_add_in_pst_tank_stores_utc_offset(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session, timezone="America/Los_Angeles")

    measurement = _record_quick_add(client, db_session, tank, "2026-01-15T14:00")

    assert measurement.recorded_at == datetime(2026, 1, 15, 22, 0, tzinfo=UTC)


def test_dst_spring_forward_in_quick_add(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session, timezone="America/New_York")

    measurement = _record_quick_add(client, db_session, tank, "2026-03-08T03:30")

    assert measurement.recorded_at == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)


def test_edit_post_interprets_input_in_tank_tz(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    from safeharbor.models.measurement import Measurement

    _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session, timezone="America/New_York")
    measurement = _seed_measurement(app, db_session, tank)

    resp = client.post(
        f"/measurements/{measurement.id}/edit",
        data={
            "value": "79.5",
            "value_unit": "degF",
            "recorded_at": "2026-01-15T14:00",
            "note": "after water change",
            "submit": "Save reading",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302
    db_session.expire_all()
    edited = db_session.get(Measurement, measurement.id)
    assert edited is not None
    assert edited.recorded_at == datetime(2026, 1, 15, 19, 0, tzinfo=UTC)


def test_default_utc_tank_behavior_unchanged(
    app: Flask,
    client: Any,
    db_session: Any,
) -> None:
    _login(client, db_session)
    _seed_reference_data(app)
    tank = _seed_tank(db_session)

    measurement = _record_quick_add(client, db_session, tank, "2026-05-01T14:00")

    assert measurement.recorded_at == datetime(2026, 5, 1, 14, 0, tzinfo=UTC)
