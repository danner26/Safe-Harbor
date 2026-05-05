"""JSON time series endpoint feeding Plotly on the tank-detail page."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import select


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="d@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_app_state(app: Any) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0


def _seed_tank_with_temp_history(app: Any, db_session: Any, n: int = 5) -> Any:
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    _seed_app_state(app)

    tank = Tank(name="Reef 90", water_type="salt")
    db_session.add(tank)
    db_session.commit()

    parameter_type = db_session.scalar(
        select(ParameterType).where(ParameterType.key == "temperature")
    )
    assert parameter_type is not None

    base = datetime.now(UTC) - timedelta(hours=12)
    for i in range(n):
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=parameter_type,
            value=Decimal(20 + i),
            value_unit="degC",
            recorded_at=base + timedelta(hours=i),
            source="manual",
            recorded_by_user_id=None,
            note=None,
        )
    db_session.commit()
    return tank


def test_chart_data_404_on_unknown_tank(client: Any, app: Any, db_session: Any) -> None:
    _login(client, db_session)
    _seed_app_state(app)

    resp = client.get(f"/tanks/{uuid4()}/chart-data?parameter=temperature&range=24h")

    assert resp.status_code == 404


def test_chart_data_400_on_unknown_parameter(client: Any, app: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temp_history(app, db_session, n=3)

    resp = client.get(f"/tanks/{tank.id}/chart-data?parameter=unobtanium&range=24h")

    assert resp.status_code == 400


def test_invalid_parameter_returns_400(client: Any, app: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temp_history(app, db_session, n=3)

    resp = client.get(f"/tanks/{tank.id}/chart-data?parameter=banana&range=24h")

    assert resp.status_code == 400


def test_chart_data_400_on_unknown_range(client: Any, app: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temp_history(app, db_session, n=3)

    resp = client.get(f"/tanks/{tank.id}/chart-data?parameter=temperature&range=forever")

    assert resp.status_code == 400


def test_chart_data_returns_json_shape(client: Any, app: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temp_history(app, db_session, n=3)

    resp = client.get(f"/tanks/{tank.id}/chart-data?parameter=temperature&range=24h")

    assert resp.status_code == 200
    payload = resp.get_json()
    assert "data" in payload
    assert isinstance(payload["data"], list)
    assert payload["data"]
    first = payload["data"][0]
    assert "recorded_at" in first
    assert "recorded_at_local" in first
    assert "value" in first


def test_chart_data_includes_both_recorded_at_and_recorded_at_local(
    client: Any,
    app: Any,
    db_session: Any,
) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temp_history(app, db_session, n=1)
    tank.timezone = "America/New_York"
    db_session.commit()

    resp = client.get(f"/tanks/{tank.id}/chart-data?parameter=temperature&range=24h")

    assert resp.status_code == 200
    payload = resp.get_json()
    first = payload["data"][0]
    assert "recorded_at" in first
    assert "recorded_at_local" in first
    assert first["recorded_at"].endswith("+00:00")
    assert first["recorded_at_local"].endswith(("-04:00", "-05:00"))


def test_chart_data_orders_ascending(client: Any, app: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank_with_temp_history(app, db_session, n=3)

    resp = client.get(f"/tanks/{tank.id}/chart-data?parameter=temperature&range=24h")

    payload = resp.get_json()
    timestamps = [row["recorded_at"] for row in payload["data"]]
    assert timestamps == sorted(timestamps)


def test_chart_data_24h_excludes_old_readings(client: Any, app: Any, db_session: Any) -> None:
    """Seed one in-window + one out-of-window; 24h range returns only one."""
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.models.tank import Tank
    from safeharbor.services import measurement_service

    _login(client, db_session)
    _seed_app_state(app)
    tank = Tank(name="X", water_type="salt")
    db_session.add(tank)
    db_session.commit()

    parameter_type = db_session.scalar(
        select(ParameterType).where(ParameterType.key == "temperature")
    )
    assert parameter_type is not None

    measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("25"),
        value_unit="degC",
        recorded_at=datetime.now(UTC) - timedelta(hours=2),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("26"),
        value_unit="degC",
        recorded_at=datetime.now(UTC) - timedelta(days=10),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()

    resp = client.get(f"/tanks/{tank.id}/chart-data?parameter=temperature&range=24h")

    payload = resp.get_json()
    assert len(payload["data"]) == 1


def test_chart_data_returns_empty_list_when_no_data(
    client: Any,
    app: Any,
    db_session: Any,
) -> None:
    from safeharbor.models.tank import Tank

    _login(client, db_session)
    _seed_app_state(app)
    tank = Tank(name="Empty", water_type="fresh")
    db_session.add(tank)
    db_session.commit()

    resp = client.get(f"/tanks/{tank.id}/chart-data?parameter=temperature&range=7d")

    assert resp.status_code == 200
    assert resp.get_json() == {"data": []}
