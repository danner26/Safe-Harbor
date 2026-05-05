"""Quick-add: GET filtered parameters, POST persists in canonical SI."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select


def _login(client, db_session):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    u = User(email="d@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(u)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
    return u


def _seed_app_state(app, db_session):
    """Run seed CLI to populate units + parameter_types."""
    runner = app.test_cli_runner()
    runner.invoke(args=["safeharbor", "seed"])


def _seed_tank(db_session, **kw):
    from safeharbor.models.tank import Tank

    t = Tank(name=kw.pop("name", "Reef 90"), water_type=kw.pop("water_type", "salt"), **kw)
    db_session.add(t)
    db_session.commit()
    return t


def _recorded_at_value(response_data: bytes) -> str:
    match = re.search(rb'name="recorded_at"[^>]*value="([^"]+)"', response_data)
    assert match is not None
    return match.group(1).decode()


def _expected_local_minute_values(before: datetime, after: datetime, timezone: str) -> set[str]:
    from zoneinfo import ZoneInfo

    zone = ZoneInfo(timezone)
    values = set()
    current = before.replace(second=0, microsecond=0)
    final = after.replace(second=0, microsecond=0)
    while current <= final:
        values.add(current.astimezone(zone).strftime("%Y-%m-%dT%H:%M"))
        current += timedelta(minutes=1)
    return values


def test_quick_add_get_requires_login(client) -> None:
    resp = client.get("/measurements/quick-add", follow_redirects=False)
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_quick_add_get_renders_form(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    _seed_tank(db_session, name="Reef 90", water_type="salt")
    resp = client.get("/measurements/quick-add")
    assert resp.status_code == 200
    assert b"Log a reading" in resp.data or b"Log reading" in resp.data
    assert b"Reef 90" in resp.data
    assert b"Temperature" in resp.data
    assert b"degC" in resp.data
    assert b'href="/measurements/quick-add"' in resp.data


def test_quick_add_parameter_select_refreshes_units_with_htmx(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    _seed_tank(db_session, name="Reef 90", water_type="salt")

    resp = client.get("/measurements/quick-add")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert 'id="parameter_key"' in body
    assert 'hx-get="/measurements/units-for-parameter/"' in body
    assert 'hx-target="#value_unit"' in body
    assert 'hx-trigger="change"' in body
    assert 'hx-include="#parameter_key"' in body
    assert 'id="value_unit"' in body


def test_quick_add_get_defaults_temperature_to_fahrenheit_for_imperial_install(
    client, app, db_session
) -> None:
    user = _login(client, db_session)
    user.preferred_units = "imperial"
    db_session.commit()
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session, name="Reef 90", water_type="salt")

    resp = client.get(f"/measurements/quick-add?tank={tank.id}&parameter=temperature")

    assert resp.status_code == 200
    assert re.search(rb'<option selected value="degF">degF</option>', resp.data)


def test_quick_add_get_defaults_recorded_at_to_tank_local_time(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(
        db_session,
        name="Lagoon",
        water_type="salt",
        timezone="America/Los_Angeles",
    )

    before = datetime.now(UTC)
    resp = client.get(f"/measurements/quick-add?tank={tank.id}")
    after = datetime.now(UTC)

    assert resp.status_code == 200
    assert _recorded_at_value(resp.data) in _expected_local_minute_values(
        before,
        after,
        "America/Los_Angeles",
    )


def test_quick_add_get_without_tank_query_defaults_recorded_at_to_selected_tank_local_time(
    client, app, db_session
) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    _seed_tank(
        db_session,
        name="Lagoon",
        water_type="salt",
        timezone="America/Los_Angeles",
    )

    before = datetime.now(UTC)
    resp = client.get("/measurements/quick-add")
    after = datetime.now(UTC)

    assert resp.status_code == 200
    assert _recorded_at_value(resp.data) in _expected_local_minute_values(
        before,
        after,
        "America/Los_Angeles",
    )


def test_edit_get_defaults_canonical_temperature_to_fahrenheit_for_imperial_install(
    client, app, db_session
) -> None:
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.services import measurement_service

    user = _login(client, db_session)
    user.preferred_units = "imperial"
    db_session.commit()
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session, name="Reef 90", water_type="salt")
    parameter_type = db_session.scalar(
        select(ParameterType).where(ParameterType.key == "temperature")
    )
    assert parameter_type is not None
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("25"),
        value_unit="degC",
        recorded_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=user.id,
        note=None,
    )
    db_session.commit()

    resp = client.get(f"/measurements/{measurement.id}/edit")

    assert resp.status_code == 200
    assert re.search(rb'<option selected value="degF">degF</option>', resp.data)
    assert re.search(rb'name="value"[^>]*value="77.0000"', resp.data)


def test_quick_add_post_persists_canonical(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session, name="Reef 90", water_type="salt")
    resp = client.post(
        "/measurements/quick-add",
        data={
            "tank_id": str(tank.id),
            "parameter_key": "temperature",
            "value": "78",
            "value_unit": "degF",
            "recorded_at": "2026-04-01T12:00",
            "note": "morning",
        },
        follow_redirects=False,
    )
    assert resp.status_code == 302
    assert "logged=1" in resp.headers["Location"]

    from safeharbor.models.measurement import Measurement

    rows = db_session.scalars(select(Measurement)).all()
    assert len(rows) == 1
    # 78°F -> 25.5556°C canonical
    assert rows[0].value == Decimal("25.5556")
    assert rows[0].note == "morning"


def test_quick_add_post_invalid_unit_for_parameter_rerenders_with_error(
    client, app, db_session
) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session)
    resp = client.post(
        "/measurements/quick-add",
        data={
            "tank_id": str(tank.id),
            "parameter_key": "ph",
            "value": "8.21",
            "value_unit": "degF",  # incompatible
            "recorded_at": "2026-04-01T12:00",
            "note": "",
        },
        follow_redirects=False,
    )
    # Form-level validation rejects; render the form with errors (200, not 302)
    assert resp.status_code == 200

    from safeharbor.models.measurement import Measurement

    assert db_session.scalars(select(Measurement)).all() == []


def test_quick_add_post_unknown_parameter_rerenders_with_error(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session)
    resp = client.post(
        "/measurements/quick-add",
        data={
            "tank_id": str(tank.id),
            "parameter_key": "unobtanium",
            "value": "1",
            "value_unit": "ppm",
            "recorded_at": "2026-04-01T12:00",
        },
    )
    assert resp.status_code == 200  # rejected at form layer; form re-renders

    from safeharbor.models.measurement import Measurement

    assert db_session.scalars(select(Measurement)).all() == []


def test_quick_add_post_note_too_long_renders_error(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session)
    resp = client.post(
        "/measurements/quick-add",
        data={
            "tank_id": str(tank.id),
            "parameter_key": "temperature",
            "value": "78",
            "value_unit": "degF",
            "recorded_at": "2026-04-01T12:00",
            "note": "x" * 257,
        },
    )
    assert resp.status_code == 200
    assert b"Field cannot be longer than 256 characters" in resp.data

    from safeharbor.models.measurement import Measurement

    assert db_session.scalars(select(Measurement)).all() == []


def test_quick_add_get_with_logged_flag_shows_confirmation(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session)
    resp = client.get(f"/measurements/quick-add?tank={tank.id}&logged=1")
    assert resp.status_code == 200
    # Confirmation pill visible
    assert b"Logged" in resp.data or b"logged" in resp.data
