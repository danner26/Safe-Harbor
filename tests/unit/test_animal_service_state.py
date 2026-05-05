"""Animal service current-state query tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import event

from safeharbor.extensions import db
from safeharbor.models.animal import Animal
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.models.tank import Tank, WaterType
from safeharbor.services import animal_service
from safeharbor.services.animal_service import create_animal
from tests.unit.animal_test_helpers import app as app
from tests.unit.animal_test_helpers import seed_animal_with_events, seed_tank_and_user


def test_current_count_sums_event_deltas(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    assert animal_service.current_count(animal) == 4


def test_current_count_after_create_individual_returns_one(app, db_session) -> None:
    tank, user = seed_tank_and_user(db_session)
    animal = create_animal(
        name="Tiny",
        species="Neon goby",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
        initial_tank=tank,
        acquired_at=datetime(2026, 4, 29, 14, 30, tzinfo=UTC),
        initial_note=None,
        recorded_by_user_id=user.id,
    )

    assert animal_service.current_count(animal) == 1


def test_current_count_after_create_group_returns_acquired_quantity(app, db_session) -> None:
    tank, user = seed_tank_and_user(db_session)
    animal = create_animal(
        name=None,
        species="Blue leg hermit crab",
        scientific_name=None,
        sex=None,
        acquired_quantity=5,
        initial_tank=tank,
        acquired_at=datetime(2026, 4, 29, 14, 30, tzinfo=UTC),
        initial_note=None,
        recorded_by_user_id=user.id,
    )

    assert animal_service.current_count(animal) == 5


def test_current_count_after_full_decease_returns_zero(app, db_session) -> None:
    tank, user = seed_tank_and_user(db_session)
    animal = create_animal(
        name="Tiny",
        species="Neon goby",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
        initial_tank=tank,
        acquired_at=datetime(2026, 4, 29, 14, 30, tzinfo=UTC),
        initial_note=None,
        recorded_by_user_id=user.id,
    )
    animal_service.mark_deceased(
        animal,
        quantity=1,
        occurred_at=datetime(2026, 4, 29, 17, 0, tzinfo=UTC),
        note=None,
        recorded_by_user_id=user.id,
    )

    assert animal_service.current_count(animal) == 0


def test_current_count_after_partial_group_decease_returns_remaining(app, db_session) -> None:
    tank, user = seed_tank_and_user(db_session)
    animal = create_animal(
        name=None,
        species="Blue leg hermit crab",
        scientific_name=None,
        sex=None,
        acquired_quantity=5,
        initial_tank=tank,
        acquired_at=datetime(2026, 4, 29, 14, 30, tzinfo=UTC),
        initial_note=None,
        recorded_by_user_id=user.id,
    )
    animal_service.mark_deceased(
        animal,
        quantity=2,
        occurred_at=datetime(2026, 4, 29, 17, 0, tzinfo=UTC),
        note=None,
        recorded_by_user_id=user.id,
    )

    assert animal_service.current_count(animal) == 3


def test_current_tank_returns_latest_acquired_or_moved_tank(app, db_session) -> None:
    animal, _, second_tank, _ = seed_animal_with_events(db_session)

    assert animal_service.current_tank(animal) == second_tank


def test_current_tank_uses_event_id_tiebreaker(app, db_session) -> None:
    source_tank, user = seed_tank_and_user(db_session)
    target_tank = Tank(name="Lagoon 40", water_type=WaterType.SALT.value)
    animal = Animal(
        name="Pip",
        species="Tailspot blenny",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add_all([target_tank, animal])
    db_session.flush()
    timestamp = datetime(2026, 4, 29, 8, 0, tzinfo=UTC)
    acquired_event = AnimalEvent(
        animal_id=animal.id,
        event_type=EventType.ACQUIRED.value,
        tank_id=source_tank.id,
        quantity_delta=1,
        occurred_at=timestamp,
        recorded_by_user_id=user.id,
        created_at=timestamp,
    )
    moved_event = AnimalEvent(
        animal_id=animal.id,
        event_type=EventType.MOVED.value,
        tank_id=target_tank.id,
        quantity_delta=None,
        occurred_at=timestamp,
        recorded_by_user_id=user.id,
        created_at=timestamp,
    )
    db_session.add_all([acquired_event, moved_event])
    db_session.commit()

    assert moved_event.id > acquired_event.id
    assert animal_service.current_tank(animal) == target_tank
    assert animal_service.animals_on_tank(source_tank) == []
    assert animal_service.animals_on_tank(target_tank) == [animal]


def test_current_tank_returns_none_when_count_is_zero(app, db_session) -> None:
    tank, _ = seed_tank_and_user(db_session)
    animal = Animal(
        name=None,
        species="Royal gramma",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add(animal)
    db_session.flush()
    db_session.add_all(
        [
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
            ),
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.DECEASED.value,
                tank_id=None,
                quantity_delta=-1,
                occurred_at=datetime(2026, 4, 29, 9, 0, tzinfo=UTC),
            ),
        ]
    )
    db_session.commit()

    assert animal_service.current_tank(animal) is None


def test_current_tank_short_circuits_when_animal_is_not_alive(app, db_session, monkeypatch) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    monkeypatch.setattr(animal_service, "is_alive", lambda checked_animal: False)

    def fail_scalar(*args, **kwargs):
        raise AssertionError("current_tank must not query for a tank when the animal is dead")

    monkeypatch.setattr(db.session, "scalar", fail_scalar)

    assert animal_service.current_tank(animal) is None


def test_is_alive_uses_positive_current_count(app, db_session) -> None:
    alive_animal, tank, _, _ = seed_animal_with_events(db_session)
    deceased_animal = Animal(
        name=None,
        species="Firefish",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add(deceased_animal)
    db_session.flush()
    db_session.add(
        AnimalEvent(
            animal_id=deceased_animal.id,
            event_type=EventType.ACQUIRED.value,
            tank_id=tank.id,
            quantity_delta=1,
            occurred_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
        )
    )
    db_session.add(
        AnimalEvent(
            animal_id=deceased_animal.id,
            event_type=EventType.DECEASED.value,
            tank_id=None,
            quantity_delta=-1,
            occurred_at=datetime(2026, 4, 29, 11, 0, tzinfo=UTC),
        )
    )
    db_session.commit()

    assert animal_service.is_alive(alive_animal) is True
    assert animal_service.is_alive(deceased_animal) is False


def test_animals_on_tank_returns_alive_animals_latest_moved_to_tank(app, db_session) -> None:
    source_tank, user = seed_tank_and_user(db_session)
    target_tank = Tank(name="Lagoon 40", water_type=WaterType.SALT.value)
    other_tank = Tank(name="Mangrove 15", water_type=WaterType.BRACKISH.value)
    target_animal = Animal(
        name="Pip",
        species="Tailspot blenny",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    moved_away = Animal(
        name="Dot",
        species="Clown goby",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add_all([target_tank, other_tank, target_animal, moved_away])
    db_session.flush()
    db_session.add_all(
        [
            AnimalEvent(
                animal_id=target_animal.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=source_tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
            AnimalEvent(
                animal_id=target_animal.id,
                event_type=EventType.MOVED.value,
                tank_id=target_tank.id,
                quantity_delta=None,
                occurred_at=datetime(2026, 4, 29, 9, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
            AnimalEvent(
                animal_id=moved_away.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=target_tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
            AnimalEvent(
                animal_id=moved_away.id,
                event_type=EventType.MOVED.value,
                tank_id=other_tank.id,
                quantity_delta=None,
                occurred_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
        ]
    )
    db_session.commit()

    assert animal_service.animals_on_tank(target_tank) == [target_animal]


def test_animals_on_tank_excludes_zero_count_animals(app, db_session) -> None:
    tank, user = seed_tank_and_user(db_session)
    animal = Animal(
        name="Moe",
        species="Nassarius snail",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add(animal)
    db_session.flush()
    db_session.add_all(
        [
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.DECEASED.value,
                tank_id=None,
                quantity_delta=-1,
                occurred_at=datetime(2026, 4, 29, 9, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
        ]
    )
    db_session.commit()

    assert animal_service.animals_on_tank(tank) == []


def test_animals_on_tank_returns_empty_for_decommissioned_tank(app, db_session) -> None:
    tank, user = seed_tank_and_user(db_session)
    tank.decommission_date = date(2026, 4, 29)
    animal = Animal(
        name="Patch",
        species="Royal gramma",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add(animal)
    db_session.flush()
    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.ACQUIRED.value,
            tank_id=tank.id,
            quantity_delta=1,
            occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
            recorded_by_user_id=user.id,
        )
    )
    db_session.commit()

    assert animal_service.animals_on_tank(tank) == []


def test_animals_on_tank_constant_queries(app, db_session) -> None:
    tank, user = seed_tank_and_user(db_session)
    animals = [
        Animal(
            name=f"Fish {index}",
            species="Green chromis",
            scientific_name=None,
            sex=None,
            acquired_quantity=1,
        )
        for index in range(6)
    ]
    db_session.add_all(animals)
    db_session.flush()
    db_session.add_all(
        [
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, index, tzinfo=UTC),
                recorded_by_user_id=user.id,
            )
            for index, animal in enumerate(animals)
        ]
    )
    db_session.commit()
    query_count = 0

    def count_query(*args) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(db.engine, "before_cursor_execute", count_query)
    try:
        tank_animals = animal_service.animals_on_tank(tank)
    finally:
        event.remove(db.engine, "before_cursor_execute", count_query)

    assert tank_animals == animals
    assert query_count <= 2
