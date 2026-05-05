"""GET /animals - livestock list view."""

from __future__ import annotations

from datetime import UTC, datetime
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


def _seed_tank(db_session: Any, *, name: str) -> Any:
    from safeharbor.models.tank import Tank, WaterType

    tank = Tank(name=name, water_type=WaterType.FRESH.value)
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_animal(
    db_session: Any,
    *,
    tank: Any,
    name: str | None,
    species: str,
    scientific_name: str | None = None,
    acquired_at: datetime,
    quantity: int = 1,
    deceased: bool = False,
) -> Any:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType

    animal = Animal(
        name=name,
        species=species,
        scientific_name=scientific_name,
        acquired_quantity=quantity,
    )
    db_session.add(animal)
    db_session.flush()
    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.ACQUIRED.value,
            tank_id=tank.id,
            quantity_delta=quantity,
            occurred_at=acquired_at,
        )
    )
    if deceased:
        db_session.add(
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.DECEASED.value,
                tank_id=None,
                quantity_delta=-quantity,
                occurred_at=datetime(2026, 4, 28, 9, 0, tzinfo=UTC),
            )
        )
    db_session.commit()
    return animal


def test_unauthenticated_redirects_to_login(client: Any) -> None:
    resp = client.get("/animals", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_empty_state(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get("/animals")

    assert resp.status_code == 200
    assert b"Your animals" in resp.data
    assert b"0 alive" in resp.data
    assert b"0 deceased" in resp.data
    assert b"across 0 tanks" in resp.data
    assert b"No animals yet" in resp.data
    assert b"add your first" in resp.data
    assert b"Add animal" in resp.data


def test_header_counts(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    nano = _seed_tank(db_session, name="Nano 12")
    _seed_animal(
        db_session,
        tank=reef,
        name="Mabel",
        species="Ocellaris clownfish",
        acquired_at=datetime(2026, 4, 26, 12, 30, tzinfo=UTC),
        quantity=2,
    )
    _seed_animal(
        db_session,
        tank=nano,
        name=None,
        species="Cleaner shrimp",
        acquired_at=datetime(2026, 4, 27, 10, 0, tzinfo=UTC),
    )
    _seed_animal(
        db_session,
        tank=reef,
        name="Old Timer",
        species="Nerite snail",
        acquired_at=datetime(2026, 4, 25, 8, 0, tzinfo=UTC),
        deceased=True,
    )

    resp = client.get("/animals")

    assert resp.status_code == 200
    assert b"2 alive" in resp.data
    assert b"1 deceased" in resp.data
    assert b"across 2 tanks" in resp.data
    assert b"Old Timer" in resp.data
    assert b"No current tank" in resp.data


def test_animals_list_renders_desktop_table_and_mobile_cards(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    _seed_animal(
        db_session,
        tank=reef,
        name="Mabel",
        species="Ocellaris clownfish",
        scientific_name="Amphiprion ocellaris",
        acquired_at=datetime(2026, 4, 26, 12, 30, tzinfo=UTC),
    )

    resp = client.get("/animals")

    assert resp.status_code == 200
    assert b"<table" in resp.data
    assert b"Name" in resp.data
    assert b"Species" in resp.data
    assert b"Tank" in resp.data
    assert b"Acquired" in resp.data
    assert b"Status" in resp.data
    assert b"Mabel" in resp.data
    assert b"Ocellaris clownfish" in resp.data
    assert b"Amphiprion ocellaris" in resp.data
    assert b"Reef 90" in resp.data
    assert b"2026-04-26" in resp.data
    assert b"Alive" in resp.data
    assert b"animal-card" in resp.data
