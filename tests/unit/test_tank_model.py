"""Tank model — defaults, enum CHECK constraints, basic field shapes."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from safeharbor.models.account import User
from safeharbor.models.tank import TANK_PROFILES, Tank, WaterType


def test_water_type_enum_values() -> None:
    assert WaterType.FRESH.value == "fresh"
    assert WaterType.SALT.value == "salt"
    assert WaterType.BRACKISH.value == "brackish"


def test_tank_profiles_v1_starter_set() -> None:
    assert TANK_PROFILES == (
        "tropical_fw_community",
        "coldwater_fw",
        "planted_fw",
        "reef_sw",
        "fowlr_sw",
        "brackish",
    )


def test_tank_can_be_persisted_with_required_fields_only(app, db_session) -> None:
    tank = Tank(name="Reef 90", water_type=WaterType.SALT.value)
    db_session.add(tank)
    db_session.commit()
    assert isinstance(tank.id, UUID)
    assert tank.profile_key == "tropical_fw_community"
    assert tank.decommission_date is None
    assert tank.image_path is None
    assert tank.created_by_user_id is None
    assert tank.created_at is not None


def test_tank_can_be_persisted_with_full_fields(app, db_session) -> None:
    creator = User(email="creator@x.com", password_hash="h")
    db_session.add(creator)
    db_session.commit()

    tank = Tank(
        name="Planted 40",
        water_type="fresh",
        profile_key="planted_fw",
        volume_liters=Decimal("60.00"),
        substrate="sand + plants",
        equipment_notes="Eheim 2217\nFluval 3.0 LED",
        created_by_user_id=creator.id,
    )
    db_session.add(tank)
    db_session.commit()

    fetched = db_session.scalar(select(Tank).where(Tank.id == tank.id))
    assert fetched is not None
    assert fetched.name == "Planted 40"
    assert fetched.profile_key == "planted_fw"
    assert fetched.volume_liters == Decimal("60.00")
    assert fetched.created_by_user_id == creator.id


def test_tank_allows_invalid_profile_key_at_model_layer(app, db_session) -> None:
    tank = Tank(name="Oddball", water_type="fresh", profile_key="not_a_known_profile")
    db_session.add(tank)
    db_session.commit()
    assert tank.profile_key == "not_a_known_profile"


def test_tank_water_type_check_constraint(app, db_session) -> None:
    bogus = Tank(name="X", water_type="lava")
    db_session.add(bogus)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_tank_decommissioned_field_persists(app, db_session) -> None:
    from datetime import date

    tank = Tank(name="Old", water_type="fresh", decommission_date=date(2024, 1, 1))
    db_session.add(tank)
    db_session.commit()
    assert tank.decommission_date == date(2024, 1, 1)
