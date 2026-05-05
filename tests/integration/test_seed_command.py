"""Idempotent seed of units, parameter_types, parameter_ranges."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from safeharbor.models.parameter_range import ParameterRange
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import TANK_PROFILES
from safeharbor.models.unit import Unit


def test_seed_creates_units(app, db_session) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0, result.output

    codes = {u.code for u in db_session.scalars(select(Unit)).all()}
    expected = {"degC", "degF", "ppt", "sg", "ppm", "mg_per_l", "dKH", "dGH", "pH"}
    assert expected.issubset(codes)


def test_seed_creates_parameter_types(app, db_session) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0

    keys = {pt.key for pt in db_session.scalars(select(ParameterType)).all()}
    expected = {
        "temperature",
        "ph",
        "salinity",
        "ammonia",
        "nitrite",
        "nitrate",
        "phosphate",
        "kh",
        "gh",
        "calcium",
        "magnesium",
    }
    assert expected == keys


def test_seed_creates_parameter_ranges(app, db_session) -> None:
    runner = app.test_cli_runner()
    runner.invoke(args=["safeharbor", "seed"])

    ranges = db_session.scalars(select(ParameterRange)).all()
    assert len(ranges) == 53


def test_seed_creates_profile_specific_parameter_ranges(app, db_session) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0, result.output

    rows = db_session.execute(
        select(
            ParameterRange.profile_key,
            ParameterRange.water_type,
            ParameterType.key,
            ParameterRange.min_value,
            ParameterRange.max_value,
        )
        .join(ParameterType)
        .order_by(ParameterRange.profile_key, ParameterType.display_order)
    ).all()
    seeded = {
        (profile_key, water_type, parameter_key): (min_value, max_value)
        for profile_key, water_type, parameter_key, min_value, max_value in rows
    }

    assert {profile_key for profile_key, *_ in rows} == set(TANK_PROFILES)
    assert {
        parameter_key for profile_key, _, parameter_key in seeded if profile_key == "reef_sw"
    } == {
        "temperature",
        "ph",
        "salinity",
        "ammonia",
        "nitrite",
        "nitrate",
        "phosphate",
        "kh",
        "calcium",
        "magnesium",
    }
    assert {
        parameter_key for profile_key, _, parameter_key in seeded if profile_key == "coldwater_fw"
    } == {
        "temperature",
        "ph",
        "ammonia",
        "nitrite",
        "nitrate",
        "phosphate",
        "kh",
        "gh",
    }
    assert ("coldwater_fw", "fresh", "salinity") not in seeded

    assert seeded[("reef_sw", "salt", "kh")] == (Decimal("8.0000"), Decimal("11.0000"))
    assert seeded[("reef_sw", "salt", "calcium")] == (
        Decimal("380.0000"),
        Decimal("450.0000"),
    )
    assert seeded[("reef_sw", "salt", "magnesium")] == (
        Decimal("1280.0000"),
        Decimal("1350.0000"),
    )
    assert seeded[("reef_sw", "salt", "nitrate")] == (
        Decimal("0.0000"),
        Decimal("5.0000"),
    )
    assert seeded[("reef_sw", "salt", "phosphate")] == (
        Decimal("0.0000"),
        Decimal("0.0500"),
    )
    assert seeded[("coldwater_fw", "fresh", "temperature")] == (
        Decimal("18.3000"),
        Decimal("22.2000"),
    )
    assert seeded[("tropical_fw_community", "fresh", "temperature")] == (
        Decimal("22.0000"),
        Decimal("28.0000"),
    )


def test_seed_is_idempotent(app, db_session) -> None:
    runner = app.test_cli_runner()
    runner.invoke(args=["safeharbor", "seed"])
    first_units = len(db_session.scalars(select(Unit)).all())
    first_pts = len(db_session.scalars(select(ParameterType)).all())
    first_ranges = len(db_session.scalars(select(ParameterRange)).all())

    runner.invoke(args=["safeharbor", "seed"])
    assert len(db_session.scalars(select(Unit)).all()) == first_units
    assert len(db_session.scalars(select(ParameterType)).all()) == first_pts
    assert len(db_session.scalars(select(ParameterRange)).all()) == first_ranges


def test_seed_echoes_summary(app) -> None:
    runner = app.test_cli_runner()
    result = runner.invoke(args=["safeharbor", "seed"])
    assert result.exit_code == 0
    assert "units" in result.output.lower()
    assert "parameter_types" in result.output.lower() or "parameter types" in result.output.lower()
    assert (
        "parameter_ranges" in result.output.lower() or "parameter ranges" in result.output.lower()
    )


def test_seed_canonical_unit_temperature_is_degc(app, db_session) -> None:
    runner = app.test_cli_runner()
    runner.invoke(args=["safeharbor", "seed"])
    temp = db_session.scalar(select(ParameterType).where(ParameterType.key == "temperature"))
    canonical = db_session.scalar(select(Unit).where(Unit.id == temp.canonical_unit_id))
    assert canonical.code == "degC"


def test_seed_canonical_unit_salinity_is_ppt(app, db_session) -> None:
    runner = app.test_cli_runner()
    runner.invoke(args=["safeharbor", "seed"])
    sal = db_session.scalar(select(ParameterType).where(ParameterType.key == "salinity"))
    canonical = db_session.scalar(select(Unit).where(Unit.id == sal.canonical_unit_id))
    assert canonical.code == "ppt"


def test_seed_calcium_is_salt_only(app, db_session) -> None:
    runner = app.test_cli_runner()
    runner.invoke(args=["safeharbor", "seed"])
    ca = db_session.scalar(select(ParameterType).where(ParameterType.key == "calcium"))
    assert ca.applies_to_water_type == "salt"
