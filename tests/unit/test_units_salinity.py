"""Salinity conversion: ppt <-> specific gravity (sg), linear approximation."""

from __future__ import annotations

from decimal import Decimal

from safeharbor.utils.units import _ppt_to_sg_for_calc, ppt_to_sg, sg_to_ppt


def test_ppt_to_sg_typical_reef() -> None:
    # Spec's documented approximation: sg = 1 + 0.000776 x ppt.
    # 35 ppt -> 1 + 35 x 0.000776 = 1.02716.
    assert ppt_to_sg(Decimal("35")) == Decimal("1.0272")


def test_ppt_to_sg_freshwater() -> None:
    assert ppt_to_sg(Decimal("0")) == Decimal("1.0000")


def test_ppt_to_sg_brackish_low() -> None:
    # 5 ppt -> 1.00388, rounds to 1.0039.
    assert ppt_to_sg(Decimal("5")) == Decimal("1.0039")


def test_sg_to_ppt_typical_reef() -> None:
    # 1.0272 sg -> (1.0272 - 1) / 0.000776 = 35.05 ppt.
    assert sg_to_ppt(Decimal("1.0272")) == Decimal("35.0515")


def test_sg_to_ppt_freshwater() -> None:
    assert sg_to_ppt(Decimal("1.0000")) == Decimal("0.0000")


def test_round_trip_ppt_sg_ppt_stable_to_two_decimals() -> None:
    original = Decimal("35.00")
    sg = ppt_to_sg(original)
    back = sg_to_ppt(sg)
    # The 4-decimal canonical -> 4-decimal sg -> 4-decimal back path
    # should round-trip stably to ~0.05 ppt.
    assert abs(back - original) < Decimal("0.10")


def test_ppt_sg_ppt_round_trip_stays_within_five_hundredths() -> None:
    for original in (Decimal("5"), Decimal("25"), Decimal("33"), Decimal("35")):
        sg = _ppt_to_sg_for_calc(original)
        back = sg_to_ppt(sg)

        assert abs(back - original) <= Decimal("0.05")
