"""Animal list behavior for animals whose latest tank is decommissioned."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="keeper@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_tank(db_session: Any, *, name: str, decommissioned: bool = False) -> Any:
    from safeharbor.models.tank import Tank, WaterType

    tank = Tank(
        name=name,
        water_type=WaterType.SALT.value,
        decommission_date=date(2026, 4, 30) if decommissioned else None,
    )
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_animal(db_session: Any, *, tank: Any, name: str, species: str) -> Any:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType

    animal = Animal(name=name, species=species, acquired_quantity=1)
    db_session.add(animal)
    db_session.flush()
    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.ACQUIRED.value,
            tank_id=tank.id,
            quantity_delta=1,
            occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
        )
    )
    db_session.commit()
    return animal


def test_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    resp = client.get("/animals", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_header_tank_count_excludes_decommissioned(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    active = _seed_tank(db_session, name="Display Reef")
    retired = _seed_tank(db_session, name="Retired Reef", decommissioned=True)
    _seed_animal(db_session, tank=active, name="Mabel", species="Ocellaris clownfish")
    _seed_animal(db_session, tank=retired, name="Beacon", species="Yellow watchman goby")

    resp = client.get("/animals")

    assert resp.status_code == 200
    assert b"2 alive" in resp.data
    assert b"across 1 tank" in resp.data


def test_list_table_tank_name_null_for_decommissioned(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    retired = _seed_tank(db_session, name="Retired Reef", decommissioned=True)
    _seed_animal(db_session, tank=retired, name="Beacon", species="Yellow watchman goby")

    resp = client.get("/animals")

    assert resp.status_code == 200
    assert b"Beacon" in resp.data
    assert b"No current tank" in resp.data
    assert b"Retired Reef" not in resp.data
