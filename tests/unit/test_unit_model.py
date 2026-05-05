"""Unit model — code uniqueness, dimension CHECK constraint, basic field shapes."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from safeharbor.models.unit import Unit, UnitDimension


def test_unit_dimension_enum_values() -> None:
    assert UnitDimension.TEMPERATURE.value == "temperature"
    assert UnitDimension.CONCENTRATION.value == "concentration"
    assert UnitDimension.SALINITY.value == "salinity"
    assert UnitDimension.ALKALINITY.value == "alkalinity"
    assert UnitDimension.HARDNESS.value == "hardness"
    assert UnitDimension.DIMENSIONLESS.value == "dimensionless"


def test_unit_can_be_persisted(app, db_session) -> None:
    u = Unit(code="degC", display="°C", dimension="temperature")
    db_session.add(u)
    db_session.commit()
    assert isinstance(u.id, UUID)
    assert u.created_at is not None
    assert u.updated_at is not None


def test_unit_code_is_unique(app, db_session) -> None:
    db_session.add(Unit(code="degC", display="°C", dimension="temperature"))
    db_session.commit()
    db_session.add(Unit(code="degC", display="°C alt", dimension="temperature"))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_unit_dimension_check_constraint(app, db_session) -> None:
    bogus = Unit(code="ly", display="ly", dimension="length")
    db_session.add(bogus)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_unit_lookup_by_code(app, db_session) -> None:
    db_session.add(Unit(code="ppm", display="ppm", dimension="concentration"))
    db_session.commit()
    found = db_session.scalar(select(Unit).where(Unit.code == "ppm"))
    assert found is not None
    assert found.display == "ppm"
