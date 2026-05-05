"""Temperature conversion: degC <-> degF, with round-trip stability."""

from __future__ import annotations

from decimal import Decimal

from safeharbor.utils.units import (
    _default_temp_unit,
    celsius_to_fahrenheit,
    fahrenheit_to_celsius,
    resolve_temp_unit,
)


def test_celsius_to_fahrenheit_freezing() -> None:
    assert celsius_to_fahrenheit(Decimal("0")) == Decimal("32.0000")


def test_celsius_to_fahrenheit_boiling() -> None:
    assert celsius_to_fahrenheit(Decimal("100")) == Decimal("212.0000")


def test_celsius_to_fahrenheit_aquarium_typical() -> None:
    # 25.4 degC ~= 77.72 degF - used in spec's exit criteria.
    assert celsius_to_fahrenheit(Decimal("25.4")) == Decimal("77.7200")


def test_fahrenheit_to_celsius_freezing() -> None:
    assert fahrenheit_to_celsius(Decimal("32")) == Decimal("0.0000")


def test_fahrenheit_to_celsius_aquarium_typical() -> None:
    assert fahrenheit_to_celsius(Decimal("78")) == Decimal("25.5556")


def test_round_trip_celsius_fahrenheit_celsius() -> None:
    original = Decimal("24.5")
    f = celsius_to_fahrenheit(original)
    back = fahrenheit_to_celsius(f)
    # 4-decimal canonical storage means we expect equality after round-trip.
    assert back == Decimal("24.5000")


def test_resolve_temp_unit_explicit_imperial() -> None:
    assert resolve_temp_unit("imperial", "en-GB") == "degF"


def test_resolve_temp_unit_explicit_metric() -> None:
    assert resolve_temp_unit("metric", "en-US") == "degC"


def test_resolve_temp_unit_locale_us_imperial() -> None:
    assert resolve_temp_unit(None, "en-US") == "degF"


def test_resolve_temp_unit_locale_uk_metric() -> None:
    assert resolve_temp_unit(None, "en-GB") == "degC"


def test_resolve_temp_unit_no_locale_metric() -> None:
    assert resolve_temp_unit(None, None) == "degC"


def test_default_temp_unit_explicit_imperial() -> None:
    assert _default_temp_unit("imperial", "en-GB") == "degF"


def test_default_temp_unit_explicit_metric() -> None:
    assert _default_temp_unit("metric", "en-US") == "degC"


def test_default_temp_unit_locale_us_imperial() -> None:
    assert _default_temp_unit(None, "en-US") == "degF"


def test_default_temp_unit_locale_non_us_metric() -> None:
    assert _default_temp_unit(None, "en-GB") == "degC"
