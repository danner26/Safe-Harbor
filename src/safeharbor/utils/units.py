"""Volume + locale helpers shared by the tanks form, settings, and (in 1c.2) measurements."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

LITERS_PER_GALLON = Decimal("3.785411784")  # US gallon (RFC 3986-style canonical constant)

_TWO_PLACES = Decimal("0.01")


def resolve_unit_pref(pref: str | None, accept_language: str | None) -> str:
    """Return 'imperial' or 'metric'.

    Explicit pref wins. None falls back to the Accept-Language header:
    'en' or 'en-US' → imperial; everything else (including missing) → metric.
    """
    if pref in ("imperial", "metric"):
        return pref
    if not accept_language:
        return "metric"
    # Take the first language tag and strip any q-value/params (e.g. "en-US;q=0.9" → "en-US").
    first_tag = accept_language.split(",", 1)[0]
    lang = first_tag.split(";", 1)[0].strip().lower()
    if lang in ("en", "en-us"):
        return "imperial"
    return "metric"


def liters_to_display(
    liters: Decimal | None,
    pref: str | None,
    accept_language: str | None,
) -> tuple[Decimal | None, str]:
    """Convert canonical liters to the user's preferred unit.

    Returns (value_in_pref_unit, unit_code). pref=None falls back to locale.
    Returns (None, unit_code) when liters is None — useful for empty form fields.
    """
    resolved = resolve_unit_pref(pref, accept_language)
    unit_code = "gal" if resolved == "imperial" else "L"
    if liters is None:
        return None, unit_code
    if resolved == "imperial":
        value = (liters / LITERS_PER_GALLON).quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    else:
        value = liters.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)
    return value, unit_code


def parse_volume_input(value: Decimal, unit_code: str) -> Decimal:
    """Convert a user-submitted volume to canonical liters for storage.

    unit_code: 'L' or 'gal'. Raises ValueError on unknown unit.
    Result is rounded to 2 decimal places (matches the column's numeric(10,2)).
    """
    if unit_code == "L":
        liters = value
    elif unit_code == "gal":
        liters = value * LITERS_PER_GALLON
    else:
        raise ValueError(f"unknown unit code: {unit_code!r}")
    return liters.quantize(_TWO_PLACES, rounding=ROUND_HALF_UP)


# Phase 1c.2: temperature, salinity, concentration helpers.

_FOUR_PLACES = Decimal("0.0001")
_EIGHT_PLACES = Decimal("0.00000001")
_NINE_FIFTHS = Decimal("9") / Decimal("5")
_THIRTY_TWO = Decimal("32")
PPT_TO_SG_SLOPE = Decimal("0.000776")  # sg ~= 1 + 0.000776 x ppt @ ~25C


def celsius_to_fahrenheit(degc: Decimal) -> Decimal:
    """Convert Celsius to Fahrenheit, quantized to 4 decimal places."""
    return (degc * _NINE_FIFTHS + _THIRTY_TWO).quantize(
        _FOUR_PLACES,
        rounding=ROUND_HALF_UP,
    )


def fahrenheit_to_celsius(degf: Decimal) -> Decimal:
    """Convert Fahrenheit to Celsius, quantized to 4 decimal places."""
    return ((degf - _THIRTY_TWO) / _NINE_FIFTHS).quantize(
        _FOUR_PLACES,
        rounding=ROUND_HALF_UP,
    )


def ppt_to_sg(ppt: Decimal) -> Decimal:
    """Convert salinity ppt to specific gravity using a linear approximation."""
    return _ppt_to_sg_for_calc(ppt).quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)


def _ppt_to_sg_for_calc(ppt: Decimal) -> Decimal:
    """Convert salinity ppt to specific gravity for internal calculations."""
    return (Decimal("1") + ppt * PPT_TO_SG_SLOPE).quantize(
        _EIGHT_PLACES,
        rounding=ROUND_HALF_UP,
    )


def sg_to_ppt(sg: Decimal) -> Decimal:
    """Convert specific gravity to salinity ppt."""
    return ((sg - Decimal("1")) / PPT_TO_SG_SLOPE).quantize(
        _FOUR_PLACES,
        rounding=ROUND_HALF_UP,
    )


def ppm_to_mg_per_l(ppm: Decimal) -> Decimal:
    """Convert ppm to mg/L, treated as equivalent for aquarium measurements."""
    return ppm.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)


def mg_per_l_to_ppm(mg_per_l: Decimal) -> Decimal:
    """Convert mg/L to ppm, treated as equivalent for aquarium measurements."""
    return mg_per_l.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)


def resolve_temp_unit(pref: str | None, accept_language: str | None) -> str:
    """Return 'degC' or 'degF' from preference and locale."""
    return _default_temp_unit(pref, accept_language)


def _default_temp_unit(pref: str | None, accept_language: str | None) -> str:
    """Return the default temperature unit from preference and locale."""
    return "degF" if resolve_unit_pref(pref, accept_language) == "imperial" else "degC"


# Per-parameter compatibility table. Values are unit codes from units.code.
_PARAMETER_UNITS: dict[str, list[str]] = {
    "temperature": ["degC", "degF"],
    "ph": ["pH"],
    "salinity": ["ppt", "sg"],
    "ammonia": ["ppm", "mg_per_l"],
    "nitrite": ["ppm", "mg_per_l"],
    "nitrate": ["ppm", "mg_per_l"],
    "phosphate": ["ppm", "mg_per_l"],
    "calcium": ["ppm", "mg_per_l"],
    "magnesium": ["ppm", "mg_per_l"],
    "kh": ["dKH"],
    "gh": ["dGH"],
}
PARAMETER_KEYS: frozenset[str] = frozenset(_PARAMETER_UNITS)


def compatible_units(parameter_key: str, water_type: str | None = None) -> list[str]:
    """Return the unit codes the form should offer for this parameter.

    water_type is reserved for future per-water-type unit narrowing.
    """
    del water_type
    if parameter_key not in _PARAMETER_UNITS:
        raise ValueError(f"unknown parameter: {parameter_key!r}")
    return list(_PARAMETER_UNITS[parameter_key])


def _quantize_measurement(value: Decimal) -> Decimal:
    return value.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP)


def _validate_parameter_unit(parameter_key: str, unit_code: str) -> None:
    if parameter_key not in _PARAMETER_UNITS:
        raise ValueError(f"unknown parameter: {parameter_key!r}")
    if unit_code not in _PARAMETER_UNITS[parameter_key]:
        raise ValueError(
            f"incompatible unit {unit_code!r} for parameter {parameter_key!r}; "
            f"valid units: {_PARAMETER_UNITS[parameter_key]}",
        )


def parse_to_canonical(value: Decimal, unit_code: str, parameter_key: str) -> Decimal:
    """Convert user-submitted value to canonical units for the given parameter."""
    _validate_parameter_unit(parameter_key, unit_code)

    if parameter_key == "temperature":
        return _quantize_measurement(value) if unit_code == "degC" else fahrenheit_to_celsius(value)
    if parameter_key == "salinity":
        return _quantize_measurement(value) if unit_code == "ppt" else sg_to_ppt(value)
    return _quantize_measurement(value)


def from_canonical(value: Decimal, target_unit: str, parameter_key: str) -> Decimal:
    """Convert a canonical-stored value to a target unit for display."""
    _validate_parameter_unit(parameter_key, target_unit)

    if parameter_key == "temperature":
        return (
            _quantize_measurement(value) if target_unit == "degC" else celsius_to_fahrenheit(value)
        )
    if parameter_key == "salinity":
        return _quantize_measurement(value) if target_unit == "ppt" else ppt_to_sg(value)
    return _quantize_measurement(value)
