"""Tank history view - paginated, filtered, login-required."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

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


def _seed_tank_with_data(db_session, n: int = 5, *, parameter_key: str = "temperature"):
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    tank = Tank(name="Reef 90", water_type="salt")
    db_session.add(tank)
    db_session.commit()

    parameter_type = db_session.scalar(
        select(ParameterType).where(ParameterType.key == parameter_key)
    )
    assert parameter_type is not None

    base = datetime(2026, 4, 1, tzinfo=UTC)
    for i in range(n):
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=parameter_type,
            value=Decimal(20 + i),
            value_unit="degC",
            recorded_at=base + timedelta(days=i),
            source="manual",
            recorded_by_user_id=None,
            note=f"reading {i}",
        )
    db_session.commit()
    return tank, parameter_type


def test_history_requires_login(client) -> None:
    resp = client.get(f"/tanks/{uuid4()}/history", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_history_404_on_unknown_tank(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)

    resp = client.get(f"/tanks/{uuid4()}/history")

    assert resp.status_code == 404


def test_history_renders_recent_first_with_parameter_display_names(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank, parameter_type = _seed_tank_with_data(db_session, n=5)

    resp = client.get(f"/tanks/{tank.id}/history")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert body.find("2026-04-05") < body.find("2026-04-01")
    assert "Temperature" in body
    assert str(parameter_type.id) not in body


def test_history_filters_by_parameter(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank, _parameter_type = _seed_tank_with_data(db_session, n=3)

    resp = client.get(f"/tanks/{tank.id}/history?parameter=temperature")
    resp_other = client.get(f"/tanks/{tank.id}/history?parameter=ph")

    assert resp.status_code == 200
    assert b"Temperature" in resp.data
    assert b"No readings match" in resp_other.data


def test_history_filters_by_date_range(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank, _parameter_type = _seed_tank_with_data(db_session, n=10)

    resp = client.get(f"/tanks/{tank.id}/history?from=2026-04-05&to=2026-04-07")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "2026-04-07" in body
    assert "2026-04-05" in body
    assert "2026-04-01" not in body
    assert "2026-04-10" not in body


def test_invalid_from_date_returns_400(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank, _parameter_type = _seed_tank_with_data(db_session, n=3)

    resp = client.get(f"/tanks/{tank.id}/history?from=not-a-date")

    assert resp.status_code == 400
    assert b"Invalid from date" in resp.data


def test_history_pagination_limits_to_50(client, app, db_session) -> None:
    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank, _parameter_type = _seed_tank_with_data(db_session, n=60)

    resp = client.get(f"/tanks/{tank.id}/history")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert body.count("<tr>") == 51
    assert "Page 1" in body
    assert "Next" in body
    assert "2026-02-09" not in body


def test_history_empty_state_when_no_readings(client, app, db_session) -> None:
    from safeharbor.models.tank import Tank

    _login(client, db_session)
    _seed_app_state(app, db_session)
    tank = Tank(name="Empty", water_type="fresh")
    db_session.add(tank)
    db_session.commit()

    resp = client.get(f"/tanks/{tank.id}/history")

    assert resp.status_code == 200
    assert b"No readings" in resp.data
