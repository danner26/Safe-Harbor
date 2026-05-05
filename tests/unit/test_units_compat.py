"""Generic measurement helpers: parse_to_canonical, from_canonical, compatible_units."""

from __future__ import annotations

from decimal import Decimal

import pytest

from safeharbor.utils.units import (
    compatible_units,
    from_canonical,
    parse_to_canonical,
)


def test_parse_to_canonical_temperature_degc_passthrough() -> None:
    assert parse_to_canonical(Decimal("25.4"), "degC", "temperature") == Decimal(
        "25.4000",
    )


def test_parse_to_canonical_temperature_degf_to_degc() -> None:
    # 78 degF -> 25.5556 degC (canonical).
    assert parse_to_canonical(Decimal("78"), "degF", "temperature") == Decimal(
        "25.5556",
    )


def test_parse_to_canonical_salinity_ppt_passthrough() -> None:
    assert parse_to_canonical(Decimal("35"), "ppt", "salinity") == Decimal("35.0000")


def test_parse_to_canonical_salinity_sg_to_ppt() -> None:
    assert parse_to_canonical(Decimal("1.0272"), "sg", "salinity") == Decimal(
        "35.0515",
    )


def test_parse_to_canonical_concentration_ppm_passthrough() -> None:
    assert parse_to_canonical(Decimal("12.5"), "ppm", "nitrate") == Decimal("12.5000")
    assert parse_to_canonical(Decimal("12.5"), "mg_per_l", "nitrate") == Decimal(
        "12.5000",
    )


def test_parse_to_canonical_ph_passthrough() -> None:
    assert parse_to_canonical(Decimal("8.21"), "pH", "ph") == Decimal("8.2100")


def test_parse_to_canonical_kh_passthrough() -> None:
    assert parse_to_canonical(Decimal("8.5"), "dKH", "kh") == Decimal("8.5000")


def test_parse_to_canonical_gh_passthrough() -> None:
    assert parse_to_canonical(Decimal("6"), "dGH", "gh") == Decimal("6.0000")


def test_parse_to_canonical_unknown_parameter_raises() -> None:
    with pytest.raises(ValueError, match="unknown parameter"):
        parse_to_canonical(Decimal("1"), "ppm", "unobtanium")


def test_parse_to_canonical_incompatible_unit_raises() -> None:
    with pytest.raises(ValueError, match="incompatible"):
        parse_to_canonical(Decimal("1"), "degF", "ph")


def test_from_canonical_temperature_to_fahrenheit() -> None:
    assert from_canonical(Decimal("25.4"), "degF", "temperature") == Decimal("77.7200")


def test_from_canonical_salinity_ppt_to_sg() -> None:
    assert from_canonical(Decimal("35"), "sg", "salinity") == Decimal("1.0272")


def test_from_canonical_passthrough() -> None:
    assert from_canonical(Decimal("12.5"), "ppm", "nitrate") == Decimal("12.5000")


def test_compatible_units_temperature() -> None:
    assert compatible_units("temperature") == ["degC", "degF"]


def test_compatible_units_ph() -> None:
    assert compatible_units("ph") == ["pH"]


def test_compatible_units_salinity() -> None:
    assert compatible_units("salinity") == ["ppt", "sg"]


def test_compatible_units_nitrate() -> None:
    assert compatible_units("nitrate") == ["ppm", "mg_per_l"]


def test_compatible_units_kh() -> None:
    assert compatible_units("kh") == ["dKH"]


def test_compatible_units_gh() -> None:
    assert compatible_units("gh") == ["dGH"]


def test_compatible_units_unknown_raises() -> None:
    with pytest.raises(ValueError, match="unknown parameter"):
        compatible_units("unobtanium")
