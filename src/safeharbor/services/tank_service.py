"""Tank CRUD + soft-decommission helpers + canonical list queries."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Literal, cast
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import aliased

from safeharbor.extensions import db
from safeharbor.models.measurement import Measurement
from safeharbor.models.parameter_range import ParameterRange
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit
from safeharbor.services import measurement_service

ParamBand = Literal["healthy", "watch", "unhealthy", "stale", "never"]
TankRollup = Literal["healthy", "watch", "unhealthy", "stale", "unknown"]
HealthRangeRow = tuple[ParameterRange | None, ParameterType, str]
LatestMeasurementRow = tuple[Measurement, str | None]


@dataclass(frozen=True)
class ParamStatus:
    """Tank health status for one water-quality parameter."""

    key: str
    display_name: str
    band: ParamBand
    latest_value: Decimal | None
    latest_unit_code: str | None
    recorded_at_utc: datetime | None
    stale_after_days: int
    age_days: int | None


@dataclass(frozen=True)
class TankHealth:
    """Computed tank-level health rollup and parameter breakdown."""

    rollup: TankRollup
    by_parameter: list[ParamStatus]


@dataclass(frozen=True)
class HistoryQueryParams:
    """Validated measurement history query parameters."""

    page: int
    page_size: int
    from_date: datetime | None
    to_date: datetime | None
    parameter_keys: tuple[str, ...]


_ROLLUP_SEVERITY: dict[TankRollup, int] = {
    "healthy": 0,
    "stale": 1,
    "watch": 2,
    "unhealthy": 3,
}


def create_tank(
    *,
    name: str,
    water_type: str,
    profile_key: str,
    volume_liters: Decimal | None,
    setup_date: date | None,
    substrate: str | None,
    equipment_notes: str | None,
    timezone: str,
    created_by_user_id: UUID | None,
) -> Tank:
    """Create a tank row. The caller commits the surrounding transaction."""
    tank = Tank(
        name=name,
        water_type=water_type,
        profile_key=profile_key,
        volume_liters=volume_liters,
        setup_date=setup_date,
        substrate=substrate or None,
        equipment_notes=equipment_notes or None,
        timezone=timezone,
        created_by_user_id=created_by_user_id,
    )
    db.session.add(tank)
    db.session.flush()  # populate tank.id
    return tank


def update_tank(
    tank: Tank,
    *,
    name: str,
    water_type: str,
    profile_key: str,
    volume_liters: Decimal | None,
    setup_date: date | None,
    substrate: str | None,
    equipment_notes: str | None,
    timezone: str,
) -> None:
    """Apply form values to an existing tank. Caller commits."""
    tank.name = name
    tank.water_type = water_type
    tank.profile_key = profile_key
    tank.volume_liters = volume_liters
    tank.setup_date = setup_date
    tank.substrate = substrate or None
    tank.equipment_notes = equipment_notes or None
    tank.timezone = timezone


def decommission(tank: Tank, *, today: date | None = None) -> None:
    """Soft-delete the tank by setting decommission_date to today (UTC)."""
    tank.decommission_date = today or datetime.now(UTC).date()


def restore(tank: Tank) -> None:
    """Un-decommission the tank by nulling decommission_date."""
    tank.decommission_date = None


def active_tanks(*, limit: int | None = None) -> list[Tank]:
    """Return active tanks ordered by created_at DESC. None limit = no LIMIT clause."""
    stmt = select(Tank).where(Tank.decommission_date.is_(None)).order_by(Tank.created_at.desc())
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.session.scalars(stmt).all())


def decommissioned_tanks(*, limit: int | None = None) -> list[Tank]:
    """Return decommissioned tanks ordered by decommission_date DESC."""
    stmt = (
        select(Tank)
        .where(Tank.decommission_date.is_not(None))
        .order_by(Tank.decommission_date.desc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    return list(db.session.scalars(stmt).all())


def get_tank_or_none_unscoped(tank_id: UUID) -> Tank | None:
    """Look up a tank by id; return None if missing. (Thin wrapper for view ergonomics.)"""
    return cast("Tank | None", db.session.get(Tank, tank_id))


def parse_history_query_params(args: Mapping[str, str]) -> HistoryQueryParams:
    """Parse and validate tank history filter query parameters."""
    parameter_key = args.get("parameter") or None
    try:
        page = max(1, int(args.get("page", "1")))
    except ValueError:
        page = 1

    return HistoryQueryParams(
        page=page,
        page_size=50,
        from_date=_parse_history_date(args.get("from") or None, field_label="from", end=False),
        to_date=_parse_history_date(args.get("to") or None, field_label="to", end=True),
        parameter_keys=() if parameter_key is None else (parameter_key,),
    )


def compute_tank_health(tank: Tank) -> TankHealth:
    """Return an on-read health rollup for a tank without mutating database state."""
    return compute_tank_health_bulk([tank])[tank.id]


def compute_tank_health_bulk(tanks: Sequence[Tank]) -> dict[UUID, TankHealth]:
    """Return on-read health rollups for tanks using two constant queries."""
    if not tanks:
        return {}
    water_types = {tank.water_type for tank in tanks}
    profile_keys = {tank.profile_key for tank in tanks}
    tank_ids = {tank.id for tank in tanks}
    with db.session.no_autoflush:
        raw_range_rows = db.session.execute(
            select(ParameterRange, ParameterType, Unit.code)
            .select_from(ParameterType)
            .join(Unit, Unit.id == ParameterType.canonical_unit_id)
            .outerjoin(
                ParameterRange,
                and_(
                    ParameterRange.parameter_type_id == ParameterType.id,
                    ParameterRange.water_type.in_(water_types),
                    ParameterRange.profile_key.in_(profile_keys),
                ),
            )
            .where(
                or_(
                    ParameterType.applies_to_water_type.is_(None),
                    ParameterType.applies_to_water_type.in_(water_types),
                )
            )
            .order_by(ParameterType.display_order, ParameterType.display_name)
        ).all()
        parameter_defs: list[tuple[ParameterType, str]] = []
        seen_parameter_ids: set[UUID] = set()
        range_by_water_type_profile_and_param: dict[tuple[str, str, UUID], ParameterRange] = {}
        for parameter_range, parameter_type, unit_code in raw_range_rows:
            if parameter_type.id not in seen_parameter_ids:
                parameter_defs.append((parameter_type, unit_code))
                seen_parameter_ids.add(parameter_type.id)
            if parameter_range is not None:
                range_by_water_type_profile_and_param[
                    (parameter_range.water_type, parameter_range.profile_key, parameter_type.id)
                ] = parameter_range

        parameter_ids = [parameter_type.id for parameter_type, _ in parameter_defs]
        range_rows_by_water_type_and_profile: dict[tuple[str, str], list[HealthRangeRow]] = {}
        for water_type in water_types:
            for profile_key in profile_keys:
                range_rows_by_water_type_and_profile[(water_type, profile_key)] = [
                    (
                        range_by_water_type_profile_and_param.get(
                            (water_type, profile_key, parameter_type.id)
                        ),
                        parameter_type,
                        unit_code,
                    )
                    for parameter_type, unit_code in parameter_defs
                    if parameter_type.applies_to_water_type in (None, water_type)
                ]
        ranked_measurements = (
            select(
                Measurement,
                func.row_number()
                .over(
                    partition_by=(Measurement.tank_id, Measurement.parameter_type_id),
                    order_by=(
                        Measurement.recorded_at.desc(),
                        Measurement.created_at.desc(),
                        Measurement.id.desc(),
                    ),
                )
                .label("rank"),
            )
            .where(Measurement.tank_id.in_(tank_ids))
            .where(Measurement.parameter_type_id.in_(parameter_ids))
            .subquery()
        )
        latest_measurement = aliased(Measurement, ranked_measurements)
        raw_unit = aliased(Unit)
        latest_rows = db.session.execute(
            select(latest_measurement, raw_unit.code)
            .outerjoin(raw_unit, raw_unit.id == latest_measurement.raw_unit_id)
            .where(ranked_measurements.c.rank == 1)
        ).all()
        latest_by_tank_id: dict[UUID, dict[UUID, LatestMeasurementRow]] = {}
        for measurement, raw_unit_code in latest_rows:
            latest_by_tank_id.setdefault(measurement.tank_id, {})[measurement.parameter_type_id] = (
                measurement,
                raw_unit_code,
            )

    health_by_tank_id: dict[UUID, TankHealth] = {}
    for tank in tanks:
        health_by_tank_id[tank.id] = _compute_health_from_rows(
            tank,
            range_rows_by_water_type_and_profile.get((tank.water_type, tank.profile_key), []),
            latest_by_tank_id.get(tank.id, {}),
        )
    return health_by_tank_id


def _compute_health_from_rows(
    tank: Tank,
    range_rows: Sequence[HealthRangeRow],
    latest_by_parameter_id: Mapping[UUID, LatestMeasurementRow],
) -> TankHealth:
    if not range_rows:
        return TankHealth(rollup="unknown", by_parameter=[])

    now = datetime.now(UTC)
    tank_age_days = _age_days(_as_utc(cast("datetime", tank.created_at)), now)
    has_any_measurement = any(
        parameter_type.id in latest_by_parameter_id for _, parameter_type, _ in range_rows
    )
    thresholds = [
        parameter_range.stale_after_days
        for parameter_range, _, _ in range_rows
        if parameter_range is not None
    ]

    statuses: list[ParamStatus] = []
    rollup: TankRollup = "healthy"
    for parameter_range, parameter_type, unit_code in range_rows:
        latest = latest_by_parameter_id.get(parameter_type.id)
        measurement = latest[0] if latest is not None else None
        raw_unit_code = latest[1] if latest is not None else None
        if parameter_range is None:
            age_days = None
            band: ParamBand = "never"
            contribution: TankRollup = "healthy"
            recorded_at_utc = None
            latest_value = None
            latest_unit_code = None
            stale_after_days = 0
        elif measurement is None:
            age_days = None
            band = "never"
            contribution = (
                "stale" if tank_age_days > parameter_range.stale_after_days else "healthy"
            )
            recorded_at_utc = None
            latest_value = None
            latest_unit_code = None
            stale_after_days = parameter_range.stale_after_days
        else:
            recorded_at_utc = _as_utc(measurement.recorded_at)
            age_days = _age_days(recorded_at_utc, now)
            latest_value = (
                measurement.raw_value
                if raw_unit_code is not None and measurement.raw_value is not None
                else measurement.value
            )
            latest_unit_code = raw_unit_code or unit_code
            stale_after_days = parameter_range.stale_after_days
            range_status = measurement_service._range_status_from_bounds(
                measurement.value,
                parameter_range.min_value,
                parameter_range.max_value,
            )
            if range_status == "danger":
                band = "unhealthy"
                contribution = "unhealthy"
            elif range_status == "caution":
                band = "watch"
                contribution = "watch"
            elif age_days > parameter_range.stale_after_days:
                band = "stale"
                contribution = "stale"
            else:
                band = "healthy"
                contribution = "healthy"

        rollup = _max_rollup(rollup, contribution)
        statuses.append(
            ParamStatus(
                key=parameter_type.key,
                display_name=parameter_type.display_name,
                band=band,
                latest_value=latest_value,
                latest_unit_code=latest_unit_code,
                recorded_at_utc=recorded_at_utc,
                stale_after_days=stale_after_days,
                age_days=age_days,
            )
        )

    if not has_any_measurement and thresholds and tank_age_days > min(thresholds):
        rollup = "unknown"
    if not thresholds:
        rollup = "unknown"

    return TankHealth(rollup=rollup, by_parameter=statuses)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_history_date(value: str | None, *, field_label: str, end: bool) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_label} date.") from exc
    return datetime.combine(parsed, time.max if end else time.min, tzinfo=UTC)


def _age_days(value: datetime, now: datetime) -> int:
    return max((now - value).days, 0)


def _max_rollup(left: TankRollup, right: TankRollup) -> TankRollup:
    if left == "unknown" or right == "unknown":
        return "unknown"
    return left if _ROLLUP_SEVERITY[left] >= _ROLLUP_SEVERITY[right] else right
