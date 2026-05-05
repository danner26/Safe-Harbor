"""Measurement service - read/write helpers for readings and chart data."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import aliased

from safeharbor.extensions import db
from safeharbor.models.account import User
from safeharbor.models.measurement import Measurement
from safeharbor.models.parameter_range import ParameterRange
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit
from safeharbor.utils.units import (
    compatible_units,
    from_canonical,
    parse_to_canonical,
    resolve_temp_unit,
)

_FOUR_PLACES = Decimal("0.0001")
_ONE_PLACE = Decimal("0.1")
_CAUTION_BAND_RATIO = Decimal("0.10")
RangeStatus = Literal["ok", "caution", "danger"]
_RANGE_TO_DELTA: dict[str, timedelta] = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "1y": timedelta(days=365),
}
_DEFAULT_KPI_DISPLAY = {
    "temperature": "Temperature",
    "ph": "pH",
    "salinity": "Salinity",
    "kh": "KH",
    "nitrate": "Nitrate",
}


@dataclass(frozen=True)
class KpiCard:
    """Prepared display data for one KPI strip card."""

    label: str
    display_value: str | None
    display_unit: str
    trend: None = None
    range_status: RangeStatus = "ok"


@dataclass(frozen=True)
class MeasurementDisplayRow:
    """Prepared display context for a measurement table row."""

    measurement: Measurement
    range_status: RangeStatus
    recorded_by: User | None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.measurement, name)

    @property
    def logged_by_display(self) -> str:
        if self.recorded_by is None:
            return "—"
        return self.recorded_by.display_username()


def record_measurement(
    *,
    tank: Tank,
    parameter_type: ParameterType,
    value: Decimal,
    value_unit: str,
    recorded_at: datetime,
    source: str,
    recorded_by_user_id: UUID | None,
    note: str | None,
) -> Measurement:
    """Convert a submitted value to canonical units and persist it.

    The caller is responsible for committing the surrounding transaction.
    """
    canonical_value = parse_to_canonical(value, value_unit, parameter_type.key)

    raw_value: Decimal | None = None
    raw_unit_id: UUID | None = None
    canonical_unit = db.session.get(Unit, parameter_type.canonical_unit_id)
    if canonical_unit is not None and value_unit != canonical_unit.code:
        raw_value = value.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)
        raw_unit = db.session.scalar(select(Unit).where(Unit.code == value_unit))
        if raw_unit is None:
            raise ValueError(f"unknown unit code: {value_unit}")
        raw_unit_id = raw_unit.id if raw_unit is not None else None

    measurement = Measurement(
        tank_id=tank.id,
        parameter_type_id=parameter_type.id,
        value=canonical_value,
        recorded_at=recorded_at,
        source=source,
        raw_value=raw_value,
        raw_unit_id=raw_unit_id,
        recorded_by_user_id=recorded_by_user_id,
        note=note or None,
    )
    db.session.add(measurement)
    db.session.flush()
    return measurement


def edit_measurement(
    measurement: Measurement,
    *,
    value: Decimal,
    value_unit: str,
    recorded_at: datetime,
    note: str | None,
) -> Measurement:
    """Update a measurement from a submitted value/unit.

    The caller is responsible for committing the surrounding transaction.
    """
    parameter_type = db.session.get(ParameterType, measurement.parameter_type_id)
    tank = db.session.get(Tank, measurement.tank_id)
    if parameter_type is None:
        raise ValueError("measurement parameter type was not found")
    if tank is None:
        raise ValueError("measurement tank was not found")

    valid_units = compatible_units(parameter_type.key, tank.water_type)
    if value_unit not in valid_units:
        raise ValueError(
            f"incompatible unit {value_unit!r} for parameter {parameter_type.key!r}; "
            f"valid units: {valid_units}",
        )

    canonical_value = parse_to_canonical(value, value_unit, parameter_type.key)
    raw_value: Decimal | None = None
    raw_unit_id: UUID | None = None
    canonical_unit = db.session.get(Unit, parameter_type.canonical_unit_id)
    if canonical_unit is not None and value_unit != canonical_unit.code:
        raw_value = value.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)
        raw_unit = db.session.scalar(select(Unit).where(Unit.code == value_unit))
        if raw_unit is None:
            raise ValueError(f"unknown unit code: {value_unit}")
        raw_unit_id = raw_unit.id

    measurement.value = canonical_value
    measurement.recorded_at = recorded_at
    measurement.raw_value = raw_value
    measurement.raw_unit_id = raw_unit_id
    measurement.note = note or None
    db.session.flush()
    return measurement


def delete_measurement(measurement: Measurement) -> None:
    """Hard-delete a measurement without committing the transaction."""
    db.session.delete(measurement)
    db.session.flush()


def parameter_display_maps() -> tuple[dict[UUID, str], dict[UUID, str]]:
    """Return parameter display names and canonical unit labels by parameter id."""
    rows = db.session.execute(
        select(ParameterType.id, ParameterType.display_name, Unit.display)
        .join(Unit, Unit.id == ParameterType.canonical_unit_id)
        .order_by(ParameterType.display_order, ParameterType.display_name)
    ).all()
    return (
        {parameter_type_id: display_name for parameter_type_id, display_name, _unit in rows},
        {parameter_type_id: unit for parameter_type_id, _display_name, unit in rows},
    )


def latest_per_parameter(tank: Tank) -> dict[str, Measurement | None]:
    """Return each known parameter key mapped to its latest reading for a tank."""
    latest_measurements = (
        select(Measurement)
        .where(Measurement.tank_id == tank.id)
        .distinct(Measurement.parameter_type_id)
        .order_by(Measurement.parameter_type_id, Measurement.recorded_at.desc())
        .subquery()
    )
    latest_measurement = aliased(Measurement, latest_measurements)
    rows = db.session.execute(
        select(ParameterType.key, latest_measurement).outerjoin(
            latest_measurement,
            latest_measurement.parameter_type_id == ParameterType.id,
        )
    )

    return dict(rows.tuples().all())


def range_check(tank: Tank, parameter_type: ParameterType, value: Decimal) -> RangeStatus:
    """Compare a value against the advisory range for a tank profile."""
    parameter_range = db.session.scalar(
        select(ParameterRange)
        .where(ParameterRange.parameter_type_id == parameter_type.id)
        .where(ParameterRange.water_type == tank.water_type)
        .where(ParameterRange.profile_key == tank.profile_key)
    )
    if parameter_range is None:
        return "ok"

    min_value = parameter_range.min_value
    max_value = parameter_range.max_value
    if value < min_value or value > max_value:
        return "danger"

    threshold = (max_value - min_value) * _CAUTION_BAND_RATIO
    if value <= min_value + threshold or value >= max_value - threshold:
        return "caution"

    return "ok"


def _range_status_from_bounds(
    value: Decimal,
    min_value: Decimal,
    max_value: Decimal,
) -> RangeStatus:
    """Compare a value against already-loaded advisory bounds."""
    if value < min_value or value > max_value:
        return "danger"

    threshold = (max_value - min_value) * _CAUTION_BAND_RATIO
    if value <= min_value + threshold or value >= max_value - threshold:
        return "caution"

    return "ok"


def display_rows_for_measurements(
    measurements: list[Measurement],
    *,
    known_tanks: list[Tank] | None = None,
) -> list[MeasurementDisplayRow]:
    """Return row display context without per-row range or user lookups."""
    if not measurements:
        return []

    tank_by_id = {tank.id: tank for tank in known_tanks or []}
    missing_tank_ids = {row.tank_id for row in measurements}.difference(tank_by_id)
    if missing_tank_ids:
        tanks = db.session.scalars(select(Tank).where(Tank.id.in_(missing_tank_ids))).all()
        tank_by_id.update({tank.id: tank for tank in tanks})

    parameter_type_ids = {row.parameter_type_id for row in measurements}
    water_types = {tank.water_type for tank in tank_by_id.values()}
    profile_keys = {tank.profile_key for tank in tank_by_id.values()}
    ranges = db.session.scalars(
        select(ParameterRange)
        .where(ParameterRange.parameter_type_id.in_(parameter_type_ids))
        .where(ParameterRange.water_type.in_(water_types))
        .where(ParameterRange.profile_key.in_(profile_keys))
    ).all()
    range_by_param_water_profile = {
        (
            parameter_range.parameter_type_id,
            parameter_range.water_type,
            parameter_range.profile_key,
        ): parameter_range
        for parameter_range in ranges
    }

    user_ids = {
        row.recorded_by_user_id for row in measurements if row.recorded_by_user_id is not None
    }
    users = db.session.scalars(select(User).where(User.id.in_(user_ids))).all() if user_ids else []
    user_by_id = {user.id: user for user in users}

    display_rows: list[MeasurementDisplayRow] = []
    for measurement in measurements:
        tank = tank_by_id.get(measurement.tank_id)
        parameter_range = (
            range_by_param_water_profile.get(
                (measurement.parameter_type_id, tank.water_type, tank.profile_key)
            )
            if tank is not None
            else None
        )
        range_status = (
            _range_status_from_bounds(
                measurement.value,
                parameter_range.min_value,
                parameter_range.max_value,
            )
            if parameter_range is not None
            else "ok"
        )
        recorded_by = (
            user_by_id.get(measurement.recorded_by_user_id)
            if measurement.recorded_by_user_id is not None
            else None
        )
        display_rows.append(
            MeasurementDisplayRow(
                measurement=measurement,
                range_status=range_status,
                recorded_by=recorded_by,
            )
        )

    return display_rows


def kpi_context(
    tank: Tank | None,
    *,
    user: Any,
    accept_language: str | None,
) -> list[KpiCard]:
    """Return KPI strip cards with preference-aware display values."""
    third_kpi = "kh" if tank is not None and tank.water_type == "fresh" else "salinity"
    kpi_keys = ["temperature", "ph", third_kpi, "nitrate"]

    parameter_types = db.session.scalars(
        select(ParameterType).order_by(ParameterType.display_order, ParameterType.display_name)
    ).all()
    units = db.session.scalars(select(Unit)).all()
    unit_display_by_id = {unit.id: unit.display for unit in units}
    unit_display_by_code = {unit.code: unit.display for unit in units}
    parameter_by_key = {parameter_type.key: parameter_type for parameter_type in parameter_types}

    latest = latest_per_parameter(tank) if tank is not None else {}
    pref = getattr(user, "preferred_units", None)
    temp_unit = resolve_temp_unit(pref, accept_language)

    cards: list[KpiCard] = []
    for key in kpi_keys:
        parameter_type = parameter_by_key.get(key)
        measurement = latest.get(key)
        label = (
            parameter_type.display_name
            if parameter_type is not None
            else _DEFAULT_KPI_DISPLAY.get(key, key)
        )
        display_unit = (
            unit_display_by_id.get(parameter_type.canonical_unit_id, "")
            if parameter_type is not None
            else ""
        )
        if key == "temperature":
            display_unit = unit_display_by_code.get(temp_unit, temp_unit)
        display_value = None

        if measurement is not None:
            value = measurement.value
            if tank is not None and parameter_type is not None:
                range_status = range_check(tank, parameter_type, value)
            else:
                range_status = "ok"
            if key == "temperature":
                value = from_canonical(value, temp_unit, parameter_key="temperature")
            display_value = str(value.quantize(_ONE_PLACE, rounding=ROUND_HALF_UP))
        else:
            range_status = "ok"

        cards.append(
            KpiCard(
                label=label,
                display_value=display_value,
                display_unit=display_unit,
                trend=None,
                range_status=range_status,
            )
        )

    return cards


def history_for_tank(
    tank: Tank,
    *,
    parameter_key: str | None = None,
    from_dt: datetime | None = None,
    to_dt: datetime | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[MeasurementDisplayRow]:
    """Return tank measurements ordered newest first, with optional filters."""
    stmt = (
        select(Measurement)
        .where(Measurement.tank_id == tank.id)
        .order_by(Measurement.recorded_at.desc())
    )

    if parameter_key is not None:
        parameter_type = db.session.scalar(
            select(ParameterType).where(ParameterType.key == parameter_key)
        )
        if parameter_type is None:
            return []
        stmt = stmt.where(Measurement.parameter_type_id == parameter_type.id)

    if from_dt is not None:
        stmt = stmt.where(Measurement.recorded_at >= from_dt)
    if to_dt is not None:
        stmt = stmt.where(Measurement.recorded_at <= to_dt)
    if limit is not None:
        stmt = stmt.limit(limit)
    if offset is not None:
        stmt = stmt.offset(offset)

    measurements = list(db.session.scalars(stmt).all())
    return display_rows_for_measurements(measurements, known_tanks=[tank])


def time_series_for_chart(
    tank: Tank,
    *,
    parameter_key: str,
    range_token: str,
) -> list[tuple[datetime, Decimal]]:
    """Return chart points in ascending time order for Plotly."""
    if range_token not in _RANGE_TO_DELTA:
        expected = ", ".join(_RANGE_TO_DELTA)
        raise ValueError(f"unknown range_token: {range_token!r} (expected one of: {expected})")

    parameter_type = db.session.scalar(
        select(ParameterType).where(ParameterType.key == parameter_key)
    )
    if parameter_type is None:
        return []

    cutoff = datetime.now(UTC) - _RANGE_TO_DELTA[range_token]
    rows = db.session.scalars(
        select(Measurement)
        .where(Measurement.tank_id == tank.id)
        .where(Measurement.parameter_type_id == parameter_type.id)
        .where(Measurement.recorded_at >= cutoff)
        .order_by(Measurement.recorded_at.asc())
    ).all()

    return [(row.recorded_at, row.value) for row in rows]


def recent_across_tanks(*, limit: int = 10) -> list[MeasurementDisplayRow]:
    """Return recent measurements across active tanks, newest first."""
    stmt = (
        select(Measurement)
        .join(Tank, Tank.id == Measurement.tank_id)
        .where(Tank.decommission_date.is_(None))
        .order_by(Measurement.recorded_at.desc())
        .limit(limit)
    )
    measurements = list(db.session.scalars(stmt).all())
    return display_rows_for_measurements(measurements)
