"""Concentration: ppm <-> mg/L treated as equivalent passthrough."""

from __future__ import annotations

from decimal import Decimal

from safeharbor.utils.units import mg_per_l_to_ppm, ppm_to_mg_per_l


def test_ppm_to_mg_per_l_passthrough() -> None:
    assert ppm_to_mg_per_l(Decimal("12.5")) == Decimal("12.5000")


def test_mg_per_l_to_ppm_passthrough() -> None:
    assert mg_per_l_to_ppm(Decimal("0.25")) == Decimal("0.2500")


def test_zero_passes_through() -> None:
    assert ppm_to_mg_per_l(Decimal("0")) == Decimal("0.0000")
    assert mg_per_l_to_ppm(Decimal("0")) == Decimal("0.0000")
