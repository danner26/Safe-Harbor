"""Unit tests for tank health rollup computation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import event

from safeharbor.models.measurement import Measurement
from safeharbor.models.parameter_range import ParameterRange
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit
from safeharbor.services import tank_service


def _now() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def _seed_unit(
    db_session: Any,
    *,
    code: str = "ppm",
    dimension: str = "concentration",
) -> Unit:
    unit = Unit(code=code, display=code, dimension=dimension)
    db_session.add(unit)
    db_session.flush()
    return unit


def _seed_tank(
    db_session: Any,
    *,
    water_type: str = "salt",
    profile_key: str = "tropical_fw_community",
    created_at: datetime | None = None,
) -> Tank:
    tank = Tank(
        name="Reef 90",
        water_type=water_type,
        profile_key=profile_key,
        created_at=created_at or _now(),
        updated_at=created_at or _now(),
    )
    db_session.add(tank)
    db_session.flush()
    return tank


def _seed_parameter(
    db_session: Any,
    unit: Unit,
    *,
    key: str,
    display_name: str | None = None,
    display_order: int = 10,
    water_type: str = "salt",
    profile_key: str = "tropical_fw_community",
    min_value: Decimal = Decimal("0.0000"),
    max_value: Decimal = Decimal("10.0000"),
    stale_after_days: int = 7,
    applies_to_water_type: str | None = None,
) -> ParameterType:
    parameter_type = ParameterType(
        key=key,
        display_name=display_name or key.title(),
        canonical_unit_id=unit.id,
        applies_to_water_type=applies_to_water_type,
        display_order=display_order,
    )
    db_session.add(parameter_type)
    db_session.flush()
    db_session.add(
        ParameterRange(
            parameter_type_id=parameter_type.id,
            water_type=water_type,
            profile_key=profile_key,
            min_value=min_value,
            max_value=max_value,
            stale_after_days=stale_after_days,
            source="test",
        )
    )
    db_session.flush()
    return parameter_type


def _seed_parameter_range(
    db_session: Any,
    parameter_type: ParameterType,
    *,
    water_type: str,
    profile_key: str,
    min_value: Decimal,
    max_value: Decimal,
    stale_after_days: int = 7,
) -> None:
    db_session.add(
        ParameterRange(
            parameter_type_id=parameter_type.id,
            water_type=water_type,
            profile_key=profile_key,
            min_value=min_value,
            max_value=max_value,
            stale_after_days=stale_after_days,
            source="test",
        )
    )
    db_session.flush()


def _seed_measurement(
    db_session: Any,
    tank: Tank,
    parameter_type: ParameterType,
    *,
    value: Decimal,
    recorded_at: datetime | None = None,
    raw_value: Decimal | None = None,
    raw_unit: Unit | None = None,
    created_at: datetime | None = None,
) -> Measurement:
    measurement = Measurement(
        tank_id=tank.id,
        parameter_type_id=parameter_type.id,
        value=value,
        recorded_at=recorded_at or _now(),
        source="manual",
        raw_value=raw_value,
        raw_unit_id=raw_unit.id if raw_unit is not None else None,
        created_at=created_at,
        updated_at=created_at,
    )
    db_session.add(measurement)
    db_session.flush()
    return measurement


def _status(health: tank_service.TankHealth, key: str) -> tank_service.ParamStatus:
    return next(status for status in health.by_parameter if status.key == key)


def test_all_healthy_recent_rolls_up_healthy(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session)
    temperature = _seed_parameter(db_session, unit, key="temperature", display_order=10)
    nitrate = _seed_parameter(db_session, unit, key="nitrate", display_order=20)
    _seed_measurement(db_session, tank, temperature, value=Decimal("5.0000"))
    _seed_measurement(db_session, tank, nitrate, value=Decimal("6.0000"))

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "healthy"
    assert [status.key for status in health.by_parameter] == ["temperature", "nitrate"]
    assert {status.band for status in health.by_parameter} == {"healthy"}
    assert _status(health, "temperature").latest_unit_code == "ppm"


def test_one_caution_rolls_up_watch(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session)
    temperature = _seed_parameter(db_session, unit, key="temperature")
    nitrate = _seed_parameter(db_session, unit, key="nitrate", display_order=20)
    _seed_measurement(db_session, tank, temperature, value=Decimal("9.5000"))
    _seed_measurement(db_session, tank, nitrate, value=Decimal("5.0000"))

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "watch"
    assert _status(health, "temperature").band == "watch"


def test_one_danger_rolls_up_unhealthy(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session)
    temperature = _seed_parameter(db_session, unit, key="temperature")
    nitrate = _seed_parameter(db_session, unit, key="nitrate", display_order=20)
    _seed_measurement(db_session, tank, temperature, value=Decimal("11.0000"))
    _seed_measurement(db_session, tank, nitrate, value=Decimal("5.0000"))

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "unhealthy"
    assert _status(health, "temperature").band == "unhealthy"


def test_all_ok_but_stale_rolls_up_stale(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session)
    temperature = _seed_parameter(db_session, unit, key="temperature", stale_after_days=7)
    _seed_measurement(
        db_session,
        tank,
        temperature,
        value=Decimal("5.0000"),
        recorded_at=_now() - timedelta(days=9),
    )

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "stale"
    assert _status(health, "temperature").band == "stale"
    assert _status(health, "temperature").age_days >= 9


def test_brand_new_tank_no_data_rolls_up_healthy(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session, created_at=_now())
    _seed_parameter(db_session, unit, key="temperature", stale_after_days=7)

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "healthy"
    assert _status(health, "temperature").band == "never"
    assert _status(health, "temperature").age_days is None


def test_old_tank_no_data_rolls_up_unknown(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session, created_at=_now() - timedelta(days=10))
    _seed_parameter(db_session, unit, key="temperature", stale_after_days=7)

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "unknown"
    assert _status(health, "temperature").band == "never"


def test_rollup_unhealthy_takes_precedence(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session)
    ammonia = _seed_parameter(db_session, unit, key="ammonia", stale_after_days=7)
    nitrate = _seed_parameter(db_session, unit, key="nitrate", display_order=20)
    _seed_measurement(
        db_session,
        tank,
        ammonia,
        value=Decimal("5.0000"),
        recorded_at=_now() - timedelta(days=9),
    )
    _seed_measurement(db_session, tank, nitrate, value=Decimal("11.0000"))

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "unhealthy"
    assert _status(health, "ammonia").band == "stale"
    assert _status(health, "nitrate").band == "unhealthy"


def test_rollup_severity_hierarchy_unhealthy_beats_watch_beats_stale_beats_healthy(
    app,
    db_session,
) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session, created_at=_now() - timedelta(days=10))
    stale = _seed_parameter(db_session, unit, key="stale", display_order=10)
    healthy = _seed_parameter(db_session, unit, key="healthy", display_order=20)
    watch = _seed_parameter(db_session, unit, key="watch", display_order=30)
    unhealthy = _seed_parameter(db_session, unit, key="unhealthy", display_order=40)
    _seed_measurement(
        db_session,
        tank,
        stale,
        value=Decimal("5.0000"),
        recorded_at=_now() - timedelta(days=9),
    )
    _seed_measurement(db_session, tank, healthy, value=Decimal("5.0000"))
    _seed_measurement(db_session, tank, watch, value=Decimal("9.5000"))
    _seed_measurement(db_session, tank, unhealthy, value=Decimal("11.0000"))

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "unhealthy"
    assert [status.band for status in health.by_parameter] == [
        "stale",
        "healthy",
        "watch",
        "unhealthy",
    ]


def test_empty_parameter_ranges_returns_unknown(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session)
    db_session.add(
        ParameterType(
            key="temperature",
            display_name="Temperature",
            canonical_unit_id=unit.id,
            display_order=10,
        )
    )
    db_session.flush()

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "unknown"
    assert [status.band for status in health.by_parameter] == ["never"]


def test_compute_tank_health_uses_profile_specific_ranges(app, db_session) -> None:
    unit = _seed_unit(db_session, code="degC", dimension="temperature")
    tropical_tank = _seed_tank(
        db_session,
        water_type="fresh",
        profile_key="tropical_fw_community",
    )
    coldwater_tank = _seed_tank(
        db_session,
        water_type="fresh",
        profile_key="coldwater_fw",
    )
    temperature = _seed_parameter(
        db_session,
        unit,
        key="temperature",
        water_type="fresh",
        profile_key="tropical_fw_community",
        min_value=Decimal("21.0000"),
        max_value=Decimal("28.0000"),
    )
    _seed_parameter_range(
        db_session,
        temperature,
        water_type="fresh",
        profile_key="coldwater_fw",
        min_value=Decimal("18.3000"),
        max_value=Decimal("22.2000"),
    )
    _seed_measurement(db_session, tropical_tank, temperature, value=Decimal("21.1000"))
    _seed_measurement(db_session, coldwater_tank, temperature, value=Decimal("21.1000"))

    tropical_health = tank_service.compute_tank_health(tropical_tank)
    coldwater_health = tank_service.compute_tank_health(coldwater_tank)

    assert tropical_health.rollup == "watch"
    assert _status(tropical_health, "temperature").band == "watch"
    assert coldwater_health.rollup == "healthy"
    assert _status(coldwater_health, "temperature").band == "healthy"


def test_bulk_returns_per_profile_correct_rollups(app, db_session) -> None:
    unit = _seed_unit(db_session, code="degC", dimension="temperature")
    tropical_tank = _seed_tank(
        db_session,
        water_type="fresh",
        profile_key="tropical_fw_community",
    )
    coldwater_tank = _seed_tank(
        db_session,
        water_type="fresh",
        profile_key="coldwater_fw",
    )
    temperature = _seed_parameter(
        db_session,
        unit,
        key="temperature",
        water_type="fresh",
        profile_key="tropical_fw_community",
        min_value=Decimal("21.0000"),
        max_value=Decimal("28.0000"),
    )
    _seed_parameter_range(
        db_session,
        temperature,
        water_type="fresh",
        profile_key="coldwater_fw",
        min_value=Decimal("18.3000"),
        max_value=Decimal("22.2000"),
    )
    _seed_measurement(db_session, tropical_tank, temperature, value=Decimal("21.1000"))
    _seed_measurement(db_session, coldwater_tank, temperature, value=Decimal("21.1000"))

    bulk_health = tank_service.compute_tank_health_bulk([tropical_tank, coldwater_tank])

    assert bulk_health[tropical_tank.id].rollup == "watch"
    assert _status(bulk_health[tropical_tank.id], "temperature").band == "watch"
    assert bulk_health[coldwater_tank.id].rollup == "healthy"
    assert _status(bulk_health[coldwater_tank.id], "temperature").band == "healthy"


def test_raw_unit_uses_raw_value_for_display(app, db_session) -> None:
    canonical_unit = _seed_unit(db_session)
    raw_unit = _seed_unit(db_session, code="ppb")
    tank = _seed_tank(db_session)
    nitrate = _seed_parameter(db_session, canonical_unit, key="nitrate")
    _seed_measurement(
        db_session,
        tank,
        nitrate,
        value=Decimal("5.0000"),
        raw_value=Decimal("5000.0000"),
        raw_unit=raw_unit,
    )

    health = tank_service.compute_tank_health(tank)
    status = _status(health, "nitrate")

    assert status.latest_value == Decimal("5000.0000")
    assert status.latest_unit_code == "ppb"
    assert status.band == "healthy"


def test_latest_measurement_tie_breaks_by_created_at(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session)
    nitrate = _seed_parameter(db_session, unit, key="nitrate")
    recorded_at = _now()
    _seed_measurement(
        db_session,
        tank,
        nitrate,
        value=Decimal("5.0000"),
        recorded_at=recorded_at,
        created_at=recorded_at,
    )
    _seed_measurement(
        db_session,
        tank,
        nitrate,
        value=Decimal("11.0000"),
        recorded_at=recorded_at,
        created_at=recorded_at + timedelta(seconds=1),
    )

    health = tank_service.compute_tank_health(tank)

    assert health.rollup == "unhealthy"
    assert _status(health, "nitrate").latest_value == Decimal("11.0000")


def test_query_count_is_exactly_two(app, db_session) -> None:
    unit = _seed_unit(db_session)
    tank = _seed_tank(db_session)
    for index in range(5):
        parameter_type = _seed_parameter(
            db_session,
            unit,
            key=f"parameter_{index}",
            display_order=index,
        )
        _seed_measurement(db_session, tank, parameter_type, value=Decimal("5.0000"))
    query_count = 0

    def count_query(*args: object) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(db_session.get_bind(), "before_cursor_execute", count_query)
    try:
        health = tank_service.compute_tank_health(tank)
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", count_query)

    assert health.rollup == "healthy"
    assert len(health.by_parameter) == 5
    assert query_count == 2


def test_compute_tank_health_bulk_returns_same_as_per_tank(app, db_session) -> None:
    unit = _seed_unit(db_session)
    fresh_tank = _seed_tank(db_session, water_type="fresh", created_at=_now())
    salt_tank = _seed_tank(db_session, water_type="salt", created_at=_now())
    brackish_tank = _seed_tank(
        db_session,
        water_type="brackish",
        created_at=_now() - timedelta(days=10),
    )
    temperature = _seed_parameter(
        db_session,
        unit,
        key="temperature",
        display_order=10,
        water_type="fresh",
        stale_after_days=7,
        applies_to_water_type=None,
    )
    db_session.add(
        ParameterRange(
            parameter_type_id=temperature.id,
            water_type="salt",
            min_value=Decimal("0.0000"),
            max_value=Decimal("10.0000"),
            stale_after_days=7,
            source="test",
        )
    )
    db_session.add(
        ParameterRange(
            parameter_type_id=temperature.id,
            water_type="brackish",
            min_value=Decimal("0.0000"),
            max_value=Decimal("10.0000"),
            stale_after_days=7,
            source="test",
        )
    )
    salinity = _seed_parameter(
        db_session,
        unit,
        key="salinity",
        display_order=20,
        water_type="salt",
        min_value=Decimal("30.0000"),
        max_value=Decimal("35.0000"),
        stale_after_days=7,
        applies_to_water_type="salt",
    )
    hardness = _seed_parameter(
        db_session,
        unit,
        key="hardness",
        display_order=30,
        water_type="brackish",
        stale_after_days=7,
        applies_to_water_type="brackish",
    )
    _seed_measurement(db_session, fresh_tank, temperature, value=Decimal("5.0000"))
    _seed_measurement(db_session, salt_tank, temperature, value=Decimal("11.0000"))
    _seed_measurement(db_session, salt_tank, salinity, value=Decimal("33.0000"))
    _seed_measurement(
        db_session,
        brackish_tank,
        hardness,
        value=Decimal("5.0000"),
        recorded_at=_now() - timedelta(days=9),
    )
    tanks = [fresh_tank, salt_tank, brackish_tank]

    bulk_health = tank_service.compute_tank_health_bulk(tanks)

    assert bulk_health == {tank.id: tank_service.compute_tank_health(tank) for tank in tanks}


def test_compute_tank_health_bulk_ignores_irrelevant_measurement_for_unknown_rollup(
    app,
    db_session,
) -> None:
    unit = _seed_unit(db_session)
    old_fresh_tank = _seed_tank(
        db_session,
        water_type="fresh",
        created_at=_now() - timedelta(days=10),
    )
    salt_tank = _seed_tank(db_session, water_type="salt")
    _seed_parameter(
        db_session,
        unit,
        key="temperature",
        water_type="fresh",
        stale_after_days=7,
        applies_to_water_type="fresh",
    )
    salinity = _seed_parameter(
        db_session,
        unit,
        key="salinity",
        water_type="salt",
        stale_after_days=7,
        applies_to_water_type="salt",
    )
    _seed_measurement(db_session, old_fresh_tank, salinity, value=Decimal("5.0000"))

    per_tank_health = tank_service.compute_tank_health(old_fresh_tank)
    bulk_health = tank_service.compute_tank_health_bulk([old_fresh_tank, salt_tank])

    assert per_tank_health.rollup == "unknown"
    assert bulk_health[old_fresh_tank.id] == per_tank_health


def test_compute_tank_health_bulk_query_count_is_constant(app, db_session) -> None:
    unit = _seed_unit(db_session)
    parameter_types = [
        _seed_parameter(db_session, unit, key=f"parameter_{index}", display_order=index)
        for index in range(5)
    ]
    tanks = [_seed_tank(db_session, water_type="salt") for _ in range(20)]
    for tank in tanks:
        for parameter_type in parameter_types:
            _seed_measurement(db_session, tank, parameter_type, value=Decimal("5.0000"))

    def count_bulk_queries(input_tanks: list[Tank]) -> int:
        query_count = 0

        def count_query(*args: object) -> None:
            nonlocal query_count
            query_count += 1

        event.listen(db_session.get_bind(), "before_cursor_execute", count_query)
        try:
            tank_service.compute_tank_health_bulk(input_tanks)
        finally:
            event.remove(db_session.get_bind(), "before_cursor_execute", count_query)
        return query_count

    assert count_bulk_queries(tanks[:1]) == 2
    assert count_bulk_queries(tanks[:5]) == 2
    assert count_bulk_queries(tanks) == 2
