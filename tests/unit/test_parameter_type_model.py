"""ParameterType model — key uniqueness, water-type CHECK, FK to units."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.unit import Unit


def _seed_unit(db_session, code: str = "degC", dimension: str = "temperature") -> Unit:
    u = Unit(code=code, display=code, dimension=dimension)
    db_session.add(u)
    db_session.commit()
    return u


def test_parameter_type_can_be_persisted(app, db_session) -> None:
    unit = _seed_unit(db_session)
    pt = ParameterType(
        key="temperature",
        display_name="Temperature",
        canonical_unit_id=unit.id,
        applies_to_water_type=None,
        display_order=10,
    )
    db_session.add(pt)
    db_session.commit()
    assert isinstance(pt.id, UUID)
    assert pt.applies_to_water_type is None
    assert pt.display_order == 10


def test_parameter_type_key_is_unique(app, db_session) -> None:
    unit = _seed_unit(db_session)
    db_session.add(ParameterType(key="ph", display_name="pH", canonical_unit_id=unit.id))
    db_session.commit()
    db_session.add(ParameterType(key="ph", display_name="pH dup", canonical_unit_id=unit.id))
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_parameter_type_water_type_check(app, db_session) -> None:
    unit = _seed_unit(db_session)
    bogus = ParameterType(
        key="x",
        display_name="X",
        canonical_unit_id=unit.id,
        applies_to_water_type="lava",
    )
    db_session.add(bogus)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_parameter_type_default_display_order_is_zero(app, db_session) -> None:
    unit = _seed_unit(db_session)
    pt = ParameterType(key="ph", display_name="pH", canonical_unit_id=unit.id)
    db_session.add(pt)
    db_session.commit()
    assert pt.display_order == 0


def test_parameter_type_canonical_unit_fk(app, db_session) -> None:
    unit = _seed_unit(db_session, code="ppm", dimension="concentration")
    pt = ParameterType(key="nitrate", display_name="Nitrate", canonical_unit_id=unit.id)
    db_session.add(pt)
    db_session.commit()
    fetched = db_session.scalar(select(ParameterType).where(ParameterType.key == "nitrate"))
    assert fetched is not None
    assert fetched.canonical_unit_id == unit.id
