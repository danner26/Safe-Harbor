"""ParameterRange model — advisory bounds per parameter, water type, and profile."""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from safeharbor.models.parameter_range import ParameterRange
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.unit import Unit


def _seed_pt(db_session, key: str = "temperature") -> ParameterType:
    u = Unit(code="degC", display="°C", dimension="temperature")
    db_session.add(u)
    db_session.commit()
    pt = ParameterType(key=key, display_name=key.title(), canonical_unit_id=u.id)
    db_session.add(pt)
    db_session.commit()
    return pt


def test_parameter_range_can_be_persisted(app, db_session) -> None:
    pt = _seed_pt(db_session)
    pr = ParameterRange(
        parameter_type_id=pt.id,
        water_type="salt",
        profile_key="reef_sw",
        min_value=Decimal("24.0"),
        max_value=Decimal("27.0"),
        stale_after_days=7,
        source="ATM Reef chart",
    )
    db_session.add(pr)
    db_session.commit()
    assert pr.id is not None
    assert pr.profile_key == "reef_sw"


def test_parameter_range_defaults_to_tropical_fw_community(app, db_session) -> None:
    pt = _seed_pt(db_session)
    pr = ParameterRange(
        parameter_type_id=pt.id,
        water_type="fresh",
        min_value=Decimal("22"),
        max_value=Decimal("28"),
        stale_after_days=7,
    )
    db_session.add(pr)
    db_session.commit()
    assert pr.profile_key == "tropical_fw_community"


def test_parameter_range_allows_invalid_profile_key_at_model_layer(app, db_session) -> None:
    pt = _seed_pt(db_session)
    pr = ParameterRange(
        parameter_type_id=pt.id,
        water_type="fresh",
        profile_key="not_a_known_profile",
        min_value=Decimal("22"),
        max_value=Decimal("28"),
        stale_after_days=7,
    )
    db_session.add(pr)
    db_session.commit()
    assert pr.profile_key == "not_a_known_profile"


def test_parameter_range_water_type_check(app, db_session) -> None:
    pt = _seed_pt(db_session)
    bogus = ParameterRange(
        parameter_type_id=pt.id,
        water_type="lava",
        min_value=Decimal("0"),
        max_value=Decimal("1"),
        stale_after_days=7,
    )
    db_session.add(bogus)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_parameter_range_unique_per_water_profile(app, db_session) -> None:
    pt = _seed_pt(db_session)
    db_session.add(
        ParameterRange(
            parameter_type_id=pt.id,
            water_type="fresh",
            profile_key="tropical_fw_community",
            min_value=Decimal("22"),
            max_value=Decimal("28"),
            stale_after_days=7,
        )
    )
    db_session.commit()
    db_session.add(
        ParameterRange(
            parameter_type_id=pt.id,
            water_type="fresh",
            profile_key="tropical_fw_community",
            min_value=Decimal("23"),
            max_value=Decimal("27"),
            stale_after_days=7,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_parameter_range_source_is_optional(app, db_session) -> None:
    pt = _seed_pt(db_session)
    pr = ParameterRange(
        parameter_type_id=pt.id,
        water_type="brackish",
        min_value=Decimal("24"),
        max_value=Decimal("28"),
        stale_after_days=7,
    )
    db_session.add(pr)
    db_session.commit()
    assert pr.source is None
