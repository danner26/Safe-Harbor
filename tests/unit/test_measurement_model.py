"""Measurement model — defaults, source CHECK, FK to tank/parameter_type."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from safeharbor.models.measurement import Measurement, MeasurementSource
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit


def test_measurement_source_enum_values() -> None:
    assert MeasurementSource.MANUAL.value == "manual"
    assert MeasurementSource.SENSOR.value == "sensor"
    assert MeasurementSource.IMPORT.value == "import"


def _seed_tank_and_pt(db_session) -> tuple[Tank, ParameterType]:
    u = Unit(code="degC", display="°C", dimension="temperature")
    db_session.add(u)
    db_session.commit()
    pt = ParameterType(key="temperature", display_name="Temperature", canonical_unit_id=u.id)
    db_session.add(pt)
    tank = Tank(name="Reef 90", water_type="salt")
    db_session.add(tank)
    db_session.commit()
    return tank, pt


def test_measurement_can_be_persisted_with_required_fields(app, db_session) -> None:
    tank, pt = _seed_tank_and_pt(db_session)
    m = Measurement(
        tank_id=tank.id,
        parameter_type_id=pt.id,
        value=Decimal("25.4"),
        recorded_at=datetime.now(UTC),
    )
    db_session.add(m)
    db_session.commit()
    assert isinstance(m.id, UUID)
    assert m.source == "manual"
    assert m.device_id is None
    assert m.import_job_id is None
    assert m.recorded_by_user_id is None
    assert m.note is None


def test_measurement_source_check_constraint(app, db_session) -> None:
    tank, pt = _seed_tank_and_pt(db_session)
    bogus = Measurement(
        tank_id=tank.id,
        parameter_type_id=pt.id,
        value=Decimal("1"),
        recorded_at=datetime.now(UTC),
        source="psychic",
    )
    db_session.add(bogus)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_measurement_with_raw_value_and_unit(app, db_session) -> None:
    tank, pt = _seed_tank_and_pt(db_session)
    raw_unit = Unit(code="degF", display="°F", dimension="temperature")
    db_session.add(raw_unit)
    db_session.commit()
    m = Measurement(
        tank_id=tank.id,
        parameter_type_id=pt.id,
        value=Decimal("25.4"),
        raw_value=Decimal("77.72"),
        raw_unit_id=raw_unit.id,
        recorded_at=datetime.now(UTC),
    )
    db_session.add(m)
    db_session.commit()
    fetched = db_session.scalar(select(Measurement).where(Measurement.id == m.id))
    assert fetched is not None
    assert fetched.raw_value == Decimal("77.7200")
    assert fetched.raw_unit_id == raw_unit.id


def test_measurement_index_exists(app, db_session) -> None:
    """The (tank_id, parameter_type_id, recorded_at DESC) index is the
    primary access path for KPI strip + chart queries."""
    from sqlalchemy import inspect

    inspector = inspect(db_session.bind)
    indexes = {idx["name"] for idx in inspector.get_indexes("measurements")}
    assert "measurements_tank_param_recorded_idx" in indexes
    assert "measurements_recorded_idx" in indexes
