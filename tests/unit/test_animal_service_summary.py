"""Animal service lifecycle row and summary tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import event

from safeharbor.extensions import db
from safeharbor.models.account import User
from safeharbor.models.animal import Animal
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.models.tank import Tank, WaterType
from safeharbor.services import animal_service
from tests.unit.animal_test_helpers import app as app
from tests.unit.animal_test_helpers import seed_animal_with_events, seed_tank_and_user


def test_lifecycle_for_orders_by_occurred_at_then_created_at(app, db_session) -> None:
    tank, _ = seed_tank_and_user(db_session)
    animal = Animal(
        name="Dot",
        species="Clown goby",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add(animal)
    db_session.flush()
    first = AnimalEvent(
        animal_id=animal.id,
        event_type=EventType.OBSERVATION.value,
        tank_id=None,
        quantity_delta=None,
        occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
        created_at=datetime(2026, 4, 29, 8, 2, tzinfo=UTC),
    )
    second = AnimalEvent(
        animal_id=animal.id,
        event_type=EventType.ACQUIRED.value,
        tank_id=tank.id,
        quantity_delta=1,
        occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
        created_at=datetime(2026, 4, 29, 8, 1, tzinfo=UTC),
    )
    third = AnimalEvent(
        animal_id=animal.id,
        event_type=EventType.HEALTH_NOTE.value,
        tank_id=None,
        quantity_delta=None,
        occurred_at=datetime(2026, 4, 29, 9, 0, tzinfo=UTC),
        created_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
    )
    db_session.add_all([first, second, third])
    db_session.commit()

    assert animal_service.lifecycle_for(animal) == [second, first, third]


def test_lifecycle_for_single_query(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)
    query_count = 0

    def count_query(*args) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(db.engine, "before_cursor_execute", count_query)
    try:
        lifecycle = animal_service.lifecycle_for(animal)
    finally:
        event.remove(db.engine, "before_cursor_execute", count_query)

    assert len(lifecycle) == 4
    assert query_count == 1


def test_lifecycle_rows_adds_logged_by_display(app, db_session) -> None:
    animal, _, _, events = seed_animal_with_events(db_session)

    rows = animal_service.lifecycle_rows(animal)

    assert [row["event"] for row in rows] == events
    assert [row["event_type"] for row in rows] == [
        EventType.ACQUIRED.value,
        EventType.HEALTH_NOTE.value,
        EventType.MOVED.value,
        EventType.DECEASED.value,
    ]
    assert [row["logged_by_display"] for row in rows] == [
        "logged by keeper",
        "logged by keeper",
        "logged by keeper",
        "logged by keeper",
    ]


def test_lifecycle_rows_omits_logged_by_when_recorder_missing(app, db_session) -> None:
    tank, _ = seed_tank_and_user(db_session)
    animal = Animal(
        name="Dot",
        species="Clown goby",
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
            recorded_by_user_id=None,
        )
    )
    db_session.commit()

    rows = animal_service.lifecycle_rows(animal)

    assert len(rows) == 1
    assert rows[0]["logged_by_display"] is None


def test_lifecycle_rows_batches_recorder_lookup(app, db_session) -> None:
    tank, _ = seed_tank_and_user(db_session)
    animal = Animal(
        name="Dot",
        species="Clown goby",
        scientific_name=None,
        sex=None,
        acquired_quantity=6,
    )
    recorders = [
        User(email=f"keeper{index}@example.com", username=f"keeper{index}", password_hash="hash")
        for index in range(6)
    ]
    db_session.add_all([animal, *recorders])
    db_session.flush()
    db_session.add_all(
        [
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, index, tzinfo=UTC),
                recorded_by_user_id=recorder.id,
            )
            for index, recorder in enumerate(recorders)
        ]
    )
    db_session.commit()
    query_count = 0

    def count_query(*args) -> None:
        nonlocal query_count
        query_count += 1

    event.listen(db.engine, "before_cursor_execute", count_query)
    try:
        rows = animal_service.lifecycle_rows(animal)
    finally:
        event.remove(db.engine, "before_cursor_execute", count_query)

    assert [row["logged_by_display"] for row in rows] == [
        f"logged by keeper{index}" for index in range(6)
    ]
    assert query_count == 2


def test_list_summary_counts_alive_deceased_and_current_tanks(app, db_session) -> None:
    source_tank, user = seed_tank_and_user(db_session)
    target_tank = Tank(name="Lagoon 40", water_type=WaterType.SALT.value)
    db_session.add(target_tank)
    db_session.flush()
    alive_in_source = Animal(
        name="Pip",
        species="Tailspot blenny",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    moved_alive = Animal(
        name="Dot",
        species="Clown goby",
        scientific_name=None,
        sex=None,
        acquired_quantity=2,
    )
    deceased = Animal(
        name="Moe",
        species="Nassarius snail",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add_all([alive_in_source, moved_alive, deceased])
    db_session.flush()
    db_session.add_all(
        [
            AnimalEvent(
                animal_id=alive_in_source.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=source_tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
            AnimalEvent(
                animal_id=moved_alive.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=source_tank.id,
                quantity_delta=2,
                occurred_at=datetime(2026, 4, 29, 8, 5, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
            AnimalEvent(
                animal_id=moved_alive.id,
                event_type=EventType.MOVED.value,
                tank_id=target_tank.id,
                quantity_delta=None,
                occurred_at=datetime(2026, 4, 29, 9, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
            AnimalEvent(
                animal_id=deceased.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=source_tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, 10, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
            AnimalEvent(
                animal_id=deceased.id,
                event_type=EventType.DECEASED.value,
                tank_id=None,
                quantity_delta=-1,
                occurred_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
        ]
    )
    db_session.commit()

    assert animal_service.list_summary() == (2, 1, 2)


def test_list_summary_excludes_decommissioned_current_tanks(app, db_session) -> None:
    source_tank, user = seed_tank_and_user(db_session)
    retired_tank = Tank(
        name="Retired Reef",
        water_type=WaterType.SALT.value,
        decommission_date=date(2026, 4, 29),
    )
    db_session.add(retired_tank)
    db_session.flush()
    active_animal = Animal(
        name="Pip",
        species="Tailspot blenny",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    retired_animal = Animal(
        name="Beacon",
        species="Yellow watchman goby",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add_all([active_animal, retired_animal])
    db_session.flush()
    db_session.add_all(
        [
            AnimalEvent(
                animal_id=active_animal.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=source_tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
            AnimalEvent(
                animal_id=retired_animal.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=retired_tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 4, 29, 8, 5, tzinfo=UTC),
                recorded_by_user_id=user.id,
            ),
        ]
    )
    db_session.commit()

    assert animal_service.list_summary() == (2, 0, 1)


def test_list_summary_constant_queries(app, db_session) -> None:
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
        summary = animal_service.list_summary()
    finally:
        event.remove(db.engine, "before_cursor_execute", count_query)

    assert summary == (6, 0, 1)
    assert query_count <= 2
