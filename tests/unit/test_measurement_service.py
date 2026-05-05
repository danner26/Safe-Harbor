"""Unit tests for measurement service range helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from safeharbor.extensions import db
from safeharbor.models.measurement import Measurement
from safeharbor.models.parameter_range import ParameterRange
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit
from safeharbor.services import measurement_service


def _seed_unit(db_session, code: str = "ppm", dimension: str = "concentration") -> Unit:
    unit = Unit(code=code, display=code, dimension=dimension)
    db_session.add(unit)
    db_session.flush()
    return unit


def _seed_parameter_type(
    db_session,
    *,
    key: str = "nitrate",
    unit: Unit | None = None,
) -> ParameterType:
    unit = unit or _seed_unit(db_session)
    parameter_type = ParameterType(
        key=key,
        display_name=key.title(),
        canonical_unit_id=unit.id,
    )
    db_session.add(parameter_type)
    db_session.flush()
    return parameter_type


def _seed_tank(db_session, *, water_type: str = "salt") -> Tank:
    tank = Tank(name="Reef 90", water_type=water_type)
    db_session.add(tank)
    db_session.flush()
    return tank


def _seed_range(
    db_session,
    parameter_type: ParameterType,
    *,
    water_type: str = "salt",
    min_value: Decimal = Decimal("0.0000"),
    max_value: Decimal = Decimal("0.5000"),
) -> ParameterRange:
    parameter_range = ParameterRange(
        parameter_type_id=parameter_type.id,
        water_type=water_type,
        min_value=min_value,
        max_value=max_value,
        stale_after_days=7,
        source="test",
    )
    db_session.add(parameter_range)
    db_session.flush()
    return parameter_range


def test_range_check_value_in_middle_returns_ok(app, db_session) -> None:
    tank = _seed_tank(db_session)
    parameter_type = _seed_parameter_type(db_session)
    _seed_range(db_session, parameter_type)

    assert measurement_service.range_check(tank, parameter_type, Decimal("0.2500")) == "ok"


def test_range_check_value_at_low_caution_band(app, db_session) -> None:
    tank = _seed_tank(db_session)
    parameter_type = _seed_parameter_type(db_session)
    _seed_range(db_session, parameter_type)

    assert measurement_service.range_check(tank, parameter_type, Decimal("0.0500")) == "caution"
    assert measurement_service.range_check(tank, parameter_type, Decimal("0.0000")) == "caution"


def test_range_check_value_at_high_caution_band(app, db_session) -> None:
    tank = _seed_tank(db_session)
    parameter_type = _seed_parameter_type(db_session)
    _seed_range(db_session, parameter_type)

    assert measurement_service.range_check(tank, parameter_type, Decimal("0.4500")) == "caution"
    assert measurement_service.range_check(tank, parameter_type, Decimal("0.5000")) == "caution"


def test_range_check_value_below_min_returns_danger(app, db_session) -> None:
    tank = _seed_tank(db_session)
    parameter_type = _seed_parameter_type(db_session)
    _seed_range(db_session, parameter_type)

    assert measurement_service.range_check(tank, parameter_type, Decimal("-0.0001")) == "danger"


def test_range_check_value_above_max_returns_danger(app, db_session) -> None:
    tank = _seed_tank(db_session)
    parameter_type = _seed_parameter_type(db_session)
    _seed_range(db_session, parameter_type)

    assert measurement_service.range_check(tank, parameter_type, Decimal("0.5001")) == "danger"


def test_range_check_no_range_defined_returns_ok(app, db_session) -> None:
    tank = _seed_tank(db_session)
    parameter_type = _seed_parameter_type(db_session)

    assert measurement_service.range_check(tank, parameter_type, Decimal("999.0000")) == "ok"


def test_kpi_context_populates_range_status(app, db_session) -> None:
    tank = _seed_tank(db_session)
    unit = _seed_unit(db_session, code="ppm", dimension="concentration")
    nitrate = _seed_parameter_type(db_session, key="nitrate", unit=unit)
    _seed_range(
        db_session,
        nitrate,
        min_value=Decimal("0.0000"),
        max_value=Decimal("0.5000"),
    )
    db_session.commit()

    measurement_service.record_measurement(
        tank=tank,
        parameter_type=nitrate,
        value=Decimal("0.5000"),
        value_unit="ppm",
        recorded_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    db.session.commit()

    cards = measurement_service.kpi_context(
        tank,
        user=SimpleNamespace(preferred_units={}),
        accept_language=None,
    )

    nitrate_card = next(card for card in cards if card.label == "Nitrate")
    missing_card = next(card for card in cards if card.label == "pH")
    assert nitrate_card.range_status == "caution"
    assert missing_card.range_status == "ok"


def test_edit_measurement_updates_canonical_value(app, db_session) -> None:
    tank = _seed_tank(db_session)
    degc = _seed_unit(db_session, code="degC", dimension="temperature")
    db_session.add(Unit(code="degF", display="degF", dimension="temperature"))
    parameter_type = _seed_parameter_type(db_session, key="temperature", unit=degc)
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("25.0000"),
        value_unit="degC",
        recorded_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note="before",
    )

    edited = measurement_service.edit_measurement(
        measurement,
        value=Decimal("78.0000"),
        value_unit="degF",
        recorded_at=datetime(2026, 5, 1, 9, 30, tzinfo=UTC),
        note="after",
    )

    assert edited is measurement
    assert measurement.value == Decimal("25.5556")
    assert measurement.recorded_at == datetime(2026, 5, 1, 9, 30, tzinfo=UTC)
    assert measurement.note == "after"


def test_edit_measurement_updates_raw_value_and_unit(app, db_session) -> None:
    tank = _seed_tank(db_session)
    degc = _seed_unit(db_session, code="degC", dimension="temperature")
    degf = _seed_unit(db_session, code="degF", dimension="temperature")
    parameter_type = _seed_parameter_type(db_session, key="temperature", unit=degc)
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("25.0000"),
        value_unit="degC",
        recorded_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )

    measurement_service.edit_measurement(
        measurement,
        value=Decimal("78.12345"),
        value_unit="degF",
        recorded_at=measurement.recorded_at,
        note=None,
    )
    assert measurement.raw_value == Decimal("78.1235")
    assert measurement.raw_unit_id == degf.id

    measurement_service.edit_measurement(
        measurement,
        value=Decimal("26.0000"),
        value_unit="degC",
        recorded_at=measurement.recorded_at,
        note=None,
    )
    assert measurement.raw_value is None
    assert measurement.raw_unit_id is None


def test_edit_measurement_rejects_incompatible_unit(app, db_session) -> None:
    tank = _seed_tank(db_session)
    ppm = _seed_unit(db_session, code="ppm", dimension="concentration")
    db_session.add(Unit(code="degC", display="degC", dimension="temperature"))
    parameter_type = _seed_parameter_type(db_session, key="nitrate", unit=ppm)
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("3.0000"),
        value_unit="ppm",
        recorded_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note="before",
    )

    with pytest.raises(ValueError, match="incompatible unit"):
        measurement_service.edit_measurement(
            measurement,
            value=Decimal("26.0000"),
            value_unit="degC",
            recorded_at=measurement.recorded_at,
            note="after",
        )

    assert measurement.value == Decimal("3.0000")
    assert measurement.note == "before"


def test_edit_measurement_does_not_commit(app, db_session, monkeypatch: pytest.MonkeyPatch) -> None:
    tank = _seed_tank(db_session)
    unit = _seed_unit(db_session, code="ppm", dimension="concentration")
    parameter_type = _seed_parameter_type(db_session, key="nitrate", unit=unit)
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("3.0000"),
        value_unit="ppm",
        recorded_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )

    def fail_commit() -> None:
        pytest.fail("edit_measurement must not commit")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    measurement_service.edit_measurement(
        measurement,
        value=Decimal("4.0000"),
        value_unit="ppm",
        recorded_at=measurement.recorded_at,
        note=None,
    )


def test_delete_measurement_removes_row(app, db_session) -> None:
    tank = _seed_tank(db_session)
    unit = _seed_unit(db_session, code="ppm", dimension="concentration")
    parameter_type = _seed_parameter_type(db_session, key="nitrate", unit=unit)
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("3.0000"),
        value_unit="ppm",
        recorded_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )
    measurement_id = measurement.id

    measurement_service.delete_measurement(measurement)

    assert db.session.scalar(select(Measurement).where(Measurement.id == measurement_id)) is None


def test_delete_measurement_does_not_commit(
    app, db_session, monkeypatch: pytest.MonkeyPatch
) -> None:
    tank = _seed_tank(db_session)
    unit = _seed_unit(db_session, code="ppm", dimension="concentration")
    parameter_type = _seed_parameter_type(db_session, key="nitrate", unit=unit)
    measurement = measurement_service.record_measurement(
        tank=tank,
        parameter_type=parameter_type,
        value=Decimal("3.0000"),
        value_unit="ppm",
        recorded_at=datetime(2026, 4, 30, 12, 0, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=None,
        note=None,
    )

    def fail_commit() -> None:
        pytest.fail("delete_measurement must not commit")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    measurement_service.delete_measurement(measurement)
