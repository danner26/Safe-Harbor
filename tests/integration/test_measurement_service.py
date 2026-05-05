"""measurement_service — record_measurement, latest_per_parameter, history,
time_series_for_chart, recent_across_tanks."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event

from safeharbor.extensions import db
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit
from safeharbor.services import measurement_service


def _seed_param(db_session, key: str, unit_code: str, dimension: str) -> ParameterType:
    u = db.session.query(Unit).filter_by(code=unit_code).one_or_none()
    if u is None:
        u = Unit(code=unit_code, display=unit_code, dimension=dimension)
        db_session.add(u)
        db_session.flush()
    pt = ParameterType(key=key, display_name=key.title(), canonical_unit_id=u.id)
    db_session.add(pt)
    db_session.flush()
    return pt


def _seed_tank(db_session, name: str = "Reef 90", water_type: str = "salt") -> Tank:
    tank = Tank(name=name, water_type=water_type)
    db_session.add(tank)
    db_session.flush()
    return tank


def test_record_measurement_persists_canonical_value(app, db_session) -> None:
    tank = _seed_tank(db_session)
    pt = _seed_param(db_session, "temperature", "degC", "temperature")
    db_session.add(Unit(code="degF", display="degF", dimension="temperature"))
    db_session.commit()

    m = measurement_service.record_measurement(
        tank=tank,
        parameter_type=pt,
        value=Decimal("78"),
        value_unit="degF",
        recorded_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note="morning reading",
    )
    db_session.commit()

    # 78°F → 25.5556°C canonical
    assert m.value == Decimal("25.5556")
    assert m.raw_value == Decimal("78.0000")
    assert m.raw_unit_id is not None
    assert m.note == "morning reading"


def test_record_measurement_unknown_value_unit_raises_without_inserting_unit(
    app, db_session
) -> None:
    tank = _seed_tank(db_session)
    pt = _seed_param(db_session, "temperature", "degC", "temperature")
    db_session.commit()
    unit_count = db.session.query(Unit).count()

    with pytest.raises(ValueError, match="unknown unit code: degF"):
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=pt,
            value=Decimal("78"),
            value_unit="degF",
            recorded_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
            source="manual",
            recorded_by_user_id=None,
            note=None,
        )

    assert db.session.query(Unit).count() == unit_count


def test_latest_per_parameter_returns_dict(app, db_session) -> None:
    tank = _seed_tank(db_session)
    temp = _seed_param(db_session, "temperature", "degC", "temperature")
    ph = _seed_param(db_session, "ph", "pH", "dimensionless")
    db_session.commit()

    measurement_service.record_measurement(
        tank=tank,
        parameter_type=temp,
        value=Decimal("25"),
        value_unit="degC",
        recorded_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=temp,
        value=Decimal("26"),
        value_unit="degC",
        recorded_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=ph,
        value=Decimal("8.21"),
        value_unit="pH",
        recorded_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()

    latest = measurement_service.latest_per_parameter(tank)
    assert latest["temperature"].value == Decimal("26.0000")
    assert latest["ph"].value == Decimal("8.2100")


def test_latest_per_parameter_missing_returns_none(app, db_session) -> None:
    tank = _seed_tank(db_session)
    _seed_param(db_session, "temperature", "degC", "temperature")
    db_session.commit()
    latest = measurement_service.latest_per_parameter(tank)
    assert latest.get("temperature") is None


def test_latest_per_parameter_single_query(app, db_session) -> None:
    tank = _seed_tank(db_session)
    parameter_specs = [
        ("temperature", "degC", "temperature"),
        ("ph", "pH", "dimensionless"),
        ("ammonia", "ppm", "concentration"),
        ("nitrite", "ppm", "concentration"),
        ("nitrate", "ppm", "concentration"),
    ]
    params = [
        _seed_param(db_session, key, unit_code, dimension)
        for key, unit_code, dimension in parameter_specs
    ]
    db_session.commit()

    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    for parameter_index, parameter_type in enumerate(params):
        unit_code = parameter_specs[parameter_index][1]
        for reading_index in range(10):
            measurement_service.record_measurement(
                tank=tank,
                parameter_type=parameter_type,
                value=Decimal(20 + parameter_index + reading_index),
                value_unit=unit_code,
                recorded_at=base + timedelta(hours=reading_index),
                source="manual",
                recorded_by_user_id=None,
                note=None,
            )
    db_session.commit()
    db_session.refresh(tank)

    query_count = 0

    def count_query(*args) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(db.engine, "before_cursor_execute", count_query)
    try:
        latest = measurement_service.latest_per_parameter(tank)
    finally:
        event.remove(db.engine, "before_cursor_execute", count_query)

    assert query_count == 1
    assert set(latest) == {parameter_type.key for parameter_type in params}
    for parameter_index, parameter_type in enumerate(params):
        assert latest[parameter_type.key] is not None
        assert latest[parameter_type.key].value == Decimal(20 + parameter_index + 9).quantize(
            Decimal("0.0001")
        )


def test_history_for_tank_orders_desc_and_limits(app, db_session) -> None:
    tank = _seed_tank(db_session)
    pt = _seed_param(db_session, "temperature", "degC", "temperature")
    db_session.commit()
    base = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    for i in range(5):
        measurement_service.record_measurement(
            tank=tank,
            parameter_type=pt,
            value=Decimal(20 + i),
            value_unit="degC",
            recorded_at=base + timedelta(days=i),
            source="manual",
            recorded_by_user_id=None,
            note=None,
        )
    db_session.commit()

    rows = measurement_service.history_for_tank(tank, limit=3)
    assert len(rows) == 3
    # Desc ordering: newest first
    assert rows[0].value == Decimal("24.0000")
    assert rows[1].value == Decimal("23.0000")
    assert rows[2].value == Decimal("22.0000")


def test_history_for_tank_filters_by_parameter_key(app, db_session) -> None:
    tank = _seed_tank(db_session)
    temp = _seed_param(db_session, "temperature", "degC", "temperature")
    ph = _seed_param(db_session, "ph", "pH", "dimensionless")
    db_session.commit()

    measurement_service.record_measurement(
        tank=tank,
        parameter_type=temp,
        value=Decimal("25"),
        value_unit="degC",
        recorded_at=datetime(2026, 4, 1, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=ph,
        value=Decimal("8"),
        value_unit="pH",
        recorded_at=datetime(2026, 4, 1, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()

    rows = measurement_service.history_for_tank(tank, parameter_key="ph")
    assert len(rows) == 1
    assert rows[0].value == Decimal("8.0000")


def test_time_series_for_chart_24h_window(app, db_session) -> None:
    tank = _seed_tank(db_session)
    pt = _seed_param(db_session, "temperature", "degC", "temperature")
    db_session.commit()
    now = datetime.now(UTC)
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=pt,
        value=Decimal("25"),
        value_unit="degC",
        recorded_at=now - timedelta(hours=2),  # in window
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=pt,
        value=Decimal("26"),
        value_unit="degC",
        recorded_at=now - timedelta(days=2),  # out of 24h window
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()

    series = measurement_service.time_series_for_chart(
        tank, parameter_key="temperature", range_token="24h"
    )
    assert len(series) == 1
    assert series[0][1] == Decimal("25.0000")


def test_time_series_for_chart_orders_ascending(app, db_session) -> None:
    tank = _seed_tank(db_session)
    pt = _seed_param(db_session, "temperature", "degC", "temperature")
    db_session.commit()
    now = datetime.now(UTC)
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=pt,
        value=Decimal("26"),
        value_unit="degC",
        recorded_at=now - timedelta(hours=2),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    measurement_service.record_measurement(
        tank=tank,
        parameter_type=pt,
        value=Decimal("25"),
        value_unit="degC",
        recorded_at=now - timedelta(hours=4),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()

    series = measurement_service.time_series_for_chart(
        tank, parameter_key="temperature", range_token="7d"
    )
    # Plotly needs ascending x for line charts
    assert len(series) == 2
    assert series[0][1] == Decimal("25.0000")
    assert series[1][1] == Decimal("26.0000")


def test_recent_across_tanks_orders_desc_limits(app, db_session) -> None:
    tank_a = _seed_tank(db_session, name="A")
    tank_b = _seed_tank(db_session, name="B")
    decommissioned = _seed_tank(db_session, name="Old")
    decommissioned.decommission_date = datetime(2026, 3, 1, tzinfo=UTC).date()
    pt = _seed_param(db_session, "temperature", "degC", "temperature")
    db_session.commit()

    base = datetime(2026, 4, 1, tzinfo=UTC)
    for i, t in enumerate([tank_a, tank_b, tank_a, tank_b]):
        measurement_service.record_measurement(
            tank=t,
            parameter_type=pt,
            value=Decimal(20 + i),
            value_unit="degC",
            recorded_at=base + timedelta(hours=i),
            source="manual",
            recorded_by_user_id=None,
            note=None,
        )
    measurement_service.record_measurement(
        tank=decommissioned,
        parameter_type=pt,
        value=Decimal("99"),
        value_unit="degC",
        recorded_at=base + timedelta(hours=99),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db_session.commit()

    rows = measurement_service.recent_across_tanks(limit=3)
    assert len(rows) == 3
    # Newest first
    assert rows[0].value == Decimal("23.0000")
    assert all(row.tank_id != decommissioned.id for row in rows)
