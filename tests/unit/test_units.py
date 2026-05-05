"""Volume conversion + locale fallback for unit preferences."""

from __future__ import annotations

from decimal import Decimal

import pytest

from safeharbor.utils.units import (
    LITERS_PER_GALLON,
    liters_to_display,
    parse_volume_input,
    resolve_unit_pref,
)


def test_constants() -> None:
    assert Decimal("3.785411784") == LITERS_PER_GALLON


def test_resolve_unit_pref_explicit_imperial_wins() -> None:
    assert resolve_unit_pref("imperial", "en-GB") == "imperial"


def test_resolve_unit_pref_explicit_metric_wins() -> None:
    assert resolve_unit_pref("metric", "en-US") == "metric"


def test_resolve_unit_pref_none_falls_back_to_locale_us() -> None:
    assert resolve_unit_pref(None, "en-US") == "imperial"


def test_resolve_unit_pref_none_falls_back_to_locale_uk() -> None:
    assert resolve_unit_pref(None, "en-GB") == "metric"


def test_resolve_unit_pref_none_no_locale_defaults_metric() -> None:
    # Be conservative when we can't tell — metric is the global default.
    assert resolve_unit_pref(None, None) == "metric"
    assert resolve_unit_pref(None, "") == "metric"


def test_resolve_unit_pref_bare_en_treated_as_imperial() -> None:
    # `en` with no region qualifier is what curl/older browsers send;
    # treat it as US English (imperial) so US users default to gallons.
    assert resolve_unit_pref(None, "en") == "imperial"


def test_resolve_unit_pref_strips_q_values() -> None:
    # Browsers send Accept-Language with quality values like "en-US;q=0.9".
    # The q-value parameter must not break locale detection.
    assert resolve_unit_pref(None, "en-US;q=0.9") == "imperial"
    assert resolve_unit_pref(None, "en-US;q=0.9,en;q=0.8") == "imperial"
    assert resolve_unit_pref(None, "fr-FR;q=0.9") == "metric"


def test_liters_to_display_metric() -> None:
    value, unit = liters_to_display(Decimal("100"), "metric", None)
    assert value == Decimal("100.00")
    assert unit == "L"


def test_liters_to_display_imperial() -> None:
    value, unit = liters_to_display(Decimal("100"), "imperial", None)
    # 100 / 3.785411784 ≈ 26.4172
    assert value == Decimal("26.42")
    assert unit == "gal"


def test_liters_to_display_none_returns_none_with_unit() -> None:
    value, unit = liters_to_display(None, "imperial", None)
    assert value is None
    assert unit == "gal"


def test_liters_to_display_locale_fallback() -> None:
    _value, unit = liters_to_display(Decimal("100"), None, "en-US")
    assert unit == "gal"


def test_parse_volume_input_liters_passthrough() -> None:
    assert parse_volume_input(Decimal("60"), "L") == Decimal("60.00")


def test_parse_volume_input_gallons_to_liters() -> None:
    # 90 gal x 3.785411784 = 340.6870605...
    result = parse_volume_input(Decimal("90"), "gal")
    assert result == Decimal("340.69")


def test_parse_volume_input_round_trip_stable_to_two_decimals() -> None:
    original = Decimal("90.00")
    liters = parse_volume_input(original, "gal")
    redisplayed, _unit = liters_to_display(liters, "imperial", None)
    assert redisplayed == original


def test_parse_volume_input_unknown_unit_raises() -> None:
    with pytest.raises(ValueError, match="unit"):
        parse_volume_input(Decimal("1"), "barrels")
