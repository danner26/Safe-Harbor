"""Batch entry - one row per applicable parameter for the tank water type."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select


def _login(client, db_session):
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="d@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_app_state(app, db_session) -> None:
    """Run seed CLI to populate units + parameter_types."""
    del db_session
    runner = app.test_cli_runner()
    result = runner.invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0


def _seed_tank(db_session, *, water_type: str = "salt", timezone: str = "UTC"):
    from safeharbor.models.tank import Tank

    tank = Tank(name="Reef 90", water_type=water_type, timezone=timezone)
    db_session.add(tank)
    db_session.commit()
    return tank


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


def test_batch_get_requires_login(client) -> None:
    resp = client.get("/measurements/batch", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_batch_get_requires_tank_query(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)

    resp = client.get("/measurements/batch", follow_redirects=False)

    assert resp.status_code in (302, 400)


def test_batch_get_renders_salt_parameters(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session, water_type="salt")

    resp = client.get(f"/measurements/batch?tank={tank.id}")

    assert resp.status_code == 200
    assert b"Temperature" in resp.data
    assert b"Salinity" in resp.data
    assert b"Calcium" in resp.data
    assert b"GH" not in resp.data


def test_batch_get_defaults_temperature_to_fahrenheit_for_imperial_install(
    client, app, db_session
) -> None:
    user = _login(client, db_session)
    user.preferred_units = "imperial"
    db_session.commit()
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session, water_type="salt")

    resp = client.get(f"/measurements/batch?tank={tank.id}")

    assert resp.status_code == 200
    assert re.search(rb'<option selected value="degF">degF</option>', resp.data)


def test_batch_get_defaults_recorded_at_to_tank_local_time(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(
        db_session,
        water_type="salt",
        timezone="America/Los_Angeles",
    )

    before = datetime.now(UTC)
    resp = client.get(f"/measurements/batch?tank={tank.id}")
    after = datetime.now(UTC)

    assert resp.status_code == 200
    assert _recorded_at_value(resp.data) in _expected_local_minute_values(
        before,
        after,
        "America/Los_Angeles",
    )


def test_batch_get_renders_freshwater_parameters(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session, water_type="fresh")

    resp = client.get(f"/measurements/batch?tank={tank.id}")

    assert resp.status_code == 200
    assert b"Temperature" in resp.data
    assert b"GH" in resp.data
    assert b"Salinity" not in resp.data
    assert b"Calcium" not in resp.data


def test_batch_post_creates_one_row_per_non_blank_field(client, app, db_session) -> None:
    user = _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session, water_type="salt")

    resp = client.post(
        f"/measurements/batch?tank={tank.id}",
        data={
            "tank_id": str(tank.id),
            "recorded_at": "2026-04-01T12:00",
            "note": "weekly batch",
            "temperature_value": "78",
            "temperature_unit": "degF",
            "ph_value": "8.21",
            "ph_unit": "pH",
            "salinity_value": "",
            "salinity_unit": "ppt",
        },
        follow_redirects=False,
    )

    assert resp.status_code == 302

    from safeharbor.models.measurement import Measurement

    rows = db_session.scalars(select(Measurement)).all()
    assert len(rows) == 2
    assert {row.value for row in rows} == {Decimal("25.5556"), Decimal("8.2100")}
    assert {row.recorded_at for row in rows} == {datetime(2026, 4, 1, 12, 0, tzinfo=UTC)}
    assert {row.note for row in rows} == {"weekly batch"}
    assert {row.recorded_by_user_id for row in rows} == {user.id}


def test_batch_post_all_blank_rerenders_with_error(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        f"/measurements/batch?tank={tank.id}",
        data={"tank_id": str(tank.id), "recorded_at": "2026-04-01T12:00"},
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert b"Enter at least one reading" in resp.data

    from safeharbor.models.measurement import Measurement

    assert db_session.scalars(select(Measurement)).all() == []


def test_batch_post_note_too_long_rerenders_field_error(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        f"/measurements/batch?tank={tank.id}",
        data={
            "tank_id": str(tank.id),
            "recorded_at": "2026-04-01T12:00",
            "note": "x" * 257,
            "temperature_value": "78",
            "temperature_unit": "degF",
        },
    )

    assert resp.status_code == 200
    assert b"Field cannot be longer than 256 characters" in resp.data

    from safeharbor.models.measurement import Measurement

    assert db_session.scalars(select(Measurement)).all() == []


def test_batch_post_atomic_on_bad_row(client, app, db_session) -> None:
    """One bad row aborts the whole batch - no partial writes."""
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = _seed_tank(db_session, water_type="salt")

    resp = client.post(
        f"/measurements/batch?tank={tank.id}",
        data={
            "tank_id": str(tank.id),
            "recorded_at": "2026-04-01T12:00",
            "temperature_value": "78",
            "temperature_unit": "degF",
            "ph_value": "8.21",
            "ph_unit": "ppm",
        },
    )

    assert resp.status_code == 200
    assert b"incompatible unit" in resp.data

    from safeharbor.models.measurement import Measurement

    assert db_session.scalars(select(Measurement)).all() == []
