"""Integration tests for the measurements landing route."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import event, select


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="keeper@example.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_app_state(app: Any, db_session: Any) -> None:
    """Run seed CLI to populate units + parameter_types."""
    del db_session
    runner = app.test_cli_runner()
    result = runner.invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0


def _seed_tank(db_session: Any, *, name: str, water_type: str = "salt") -> Any:
    from safeharbor.models.tank import Tank

    tank = Tank(name=name, water_type=water_type)
    db_session.add(tank)
    db_session.commit()
    return tank


def _record_temperature(db_session: Any, tank: Any, *, recorded_at: datetime) -> None:
    from safeharbor.models.parameter_type import ParameterType
    from safeharbor.services import measurement_service

    temperature = db_session.scalar(select(ParameterType).where(ParameterType.key == "temperature"))
    assert temperature is not None
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=temperature,
        value=Decimal("25.0"),
        value_unit="degC",
        recorded_at=recorded_at,
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()


def test_index_renders_empty_state_when_no_tanks(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get("/measurements")

    assert resp.status_code == 200
    assert b"No tanks yet" in resp.data
    assert b"create one to start logging readings" in resp.data
    assert b'href="/tanks/new"' in resp.data
    assert b"Add a tank" in resp.data


def test_index_renders_picker_with_any_tanks(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")

    resp = client.get("/measurements")

    assert resp.status_code == 200
    assert b"Pick a tank" in resp.data
    assert b"Reef 90" in resp.data
    assert f'href="/measurements/quick-add?tank={reef.id}"'.encode() in resp.data
    assert f'href="/measurements/batch?tank={reef.id}"'.encode() in resp.data

    lagoon = _seed_tank(db_session, name="Lagoon", water_type="fresh")

    resp = client.get("/measurements")

    assert resp.status_code == 200
    assert b"Pick a tank" in resp.data
    assert b"Reef 90" in resp.data
    assert b"Lagoon" in resp.data
    assert f'href="/measurements/quick-add?tank={reef.id}"'.encode() in resp.data
    assert f'href="/measurements/quick-add?tank={lagoon.id}"'.encode() in resp.data
    assert f'href="/measurements/batch?tank={reef.id}"'.encode() in resp.data
    assert f'href="/measurements/batch?tank={lagoon.id}"'.encode() in resp.data


def test_index_latest_summary_query_count_does_not_grow_with_tank_count(
    client: Any,
    app: Any,
    db_session: Any,
) -> None:
    from safeharbor.extensions import db

    _login(client, db_session)
    _seed_app_state(app, db_session)

    base = datetime(2026, 5, 2, 12, 0, tzinfo=UTC)

    def add_tanks(start: int, stop: int) -> None:
        for index in range(start, stop):
            tank = _seed_tank(db_session, name=f"Tank {index}")
            _record_temperature(
                db_session,
                tank,
                recorded_at=base + timedelta(minutes=index),
            )

    def count_index_queries() -> int:
        query_count = 0

        def before_cursor_execute(*args: Any) -> None:
            nonlocal query_count
            query_count += 1

        event.listen(db.engine, "before_cursor_execute", before_cursor_execute)
        try:
            response = client.get("/measurements")
        finally:
            event.remove(db.engine, "before_cursor_execute", before_cursor_execute)
        assert response.status_code == 200
        return query_count

    add_tanks(0, 1)
    one_tank_query_count = count_index_queries()

    add_tanks(1, 5)
    five_tank_query_count = count_index_queries()

    assert five_tank_query_count == one_tank_query_count
    assert five_tank_query_count <= 5


def test_index_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    resp = client.get("/measurements", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location
