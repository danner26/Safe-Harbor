"""Animal service lifecycle operation tests."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from safeharbor.extensions import db
from safeharbor.models.account import User
from safeharbor.models.animal import Animal, Sex
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.models.tank import Tank, WaterType
from safeharbor.services import animal_service
from safeharbor.services.animal_service import create_animal
from tests.unit.animal_test_helpers import app as app
from tests.unit.animal_test_helpers import seed_animal_with_events, seed_tank_and_user


def test_create_animal(app, db_session) -> None:
    tank, user = seed_tank_and_user(db_session)
    acquired_at = datetime(2026, 4, 29, 14, 30, tzinfo=UTC)

    animal = create_animal(
        name="Mabel",
        species="Ocellaris clownfish",
        scientific_name="Amphiprion ocellaris",
        sex=Sex.FEMALE.value,
        acquired_quantity=2,
        initial_tank=tank,
        acquired_at=acquired_at,
        initial_note="Captive-bred pair.",
        recorded_by_user_id=user.id,
    )

    assert isinstance(animal, Animal)
    assert animal.id is not None
    assert animal.name == "Mabel"
    assert animal.species == "Ocellaris clownfish"
    assert animal.scientific_name == "Amphiprion ocellaris"
    assert animal.sex == Sex.FEMALE.value
    assert animal.acquired_quantity == 2
    assert animal.notes is None

    event = db_session.scalar(select(AnimalEvent).where(AnimalEvent.animal_id == animal.id))
    assert event is not None
    assert event.event_type == EventType.ACQUIRED.value
    assert event.tank_id == tank.id
    assert event.quantity_delta == 2
    assert event.occurred_at.replace(tzinfo=UTC) == acquired_at
    assert event.note == "Captive-bred pair."
    assert event.recorded_by_user_id == user.id


def test_create_animal_does_not_commit(app, db_session, monkeypatch) -> None:
    tank, user = seed_tank_and_user(db_session)

    def fail_commit() -> None:
        raise AssertionError("create_animal must not commit")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    animal = create_animal(
        name=None,
        species="Royal gramma",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
        initial_tank=tank,
        acquired_at=datetime(2026, 4, 29, 15, 0, tzinfo=UTC),
        initial_note="",
        recorded_by_user_id=user.id,
    )

    assert animal.id is not None
    event = db_session.scalar(select(AnimalEvent).where(AnimalEvent.animal_id == animal.id))
    assert event is not None
    assert event.note is None


def test_record_event_creates_observation_event(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)
    user = db_session.scalar(select(User).where(User.email == "keeper@example.com"))
    observed_at = datetime(2026, 4, 29, 18, 0, tzinfo=UTC)

    observation = animal_service.record_event(
        animal,
        event_type=EventType.OBSERVATION,
        tank_id=None,
        quantity_delta=None,
        occurred_at=observed_at,
        note="Bolder during feeding.",
        recorded_by_user_id=user.id,
    )

    assert isinstance(observation, AnimalEvent)
    assert observation.id is not None
    assert observation.animal_id == animal.id
    assert observation.event_type == EventType.OBSERVATION.value
    assert observation.tank_id is None
    assert observation.quantity_delta is None
    assert observation.occurred_at.replace(tzinfo=UTC) == observed_at
    assert observation.note == "Bolder during feeding."
    assert observation.recorded_by_user_id == user.id
    assert (
        db_session.scalar(select(AnimalEvent).where(AnimalEvent.id == observation.id))
        == observation
    )


def test_record_event_normalizes_blank_note(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    event = animal_service.record_event(
        animal,
        event_type=EventType.HEALTH_NOTE.value,
        tank_id=None,
        quantity_delta=None,
        occurred_at=datetime(2026, 4, 29, 18, 0, tzinfo=UTC),
        note="",
        recorded_by_user_id=None,
    )

    assert event.event_type == EventType.HEALTH_NOTE.value
    assert event.note is None


@pytest.mark.parametrize(
    "event_type",
    [
        EventType.ACQUIRED,
        EventType.MOVED.value,
        EventType.DECEASED,
        "fed",
    ],
)
def test_record_event_rejects_lifecycle_and_unknown_event_types(
    app, db_session, event_type
) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    with pytest.raises(ValueError, match="health_note or observation"):
        animal_service.record_event(
            animal,
            event_type=event_type,
            tank_id=None,
            quantity_delta=None,
            occurred_at=datetime(2026, 4, 29, 18, 0, tzinfo=UTC),
            note=None,
            recorded_by_user_id=None,
        )


def test_record_event_rejects_tank_or_quantity_for_generic_events(app, db_session) -> None:
    animal, tank, _, _ = seed_animal_with_events(db_session)

    with pytest.raises(ValueError, match="tank_id"):
        animal_service.record_event(
            animal,
            event_type=EventType.OBSERVATION,
            tank_id=tank.id,
            quantity_delta=None,
            occurred_at=datetime(2026, 4, 29, 18, 0, tzinfo=UTC),
            note=None,
            recorded_by_user_id=None,
        )

    with pytest.raises(ValueError, match="quantity_delta"):
        animal_service.record_event(
            animal,
            event_type=EventType.HEALTH_NOTE,
            tank_id=None,
            quantity_delta=1,
            occurred_at=datetime(2026, 4, 29, 18, 5, tzinfo=UTC),
            note=None,
            recorded_by_user_id=None,
        )


def test_record_event_does_not_commit(app, db_session, monkeypatch) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    def fail_commit() -> None:
        raise AssertionError("record_event must not commit")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    event = animal_service.record_event(
        animal,
        event_type=EventType.OBSERVATION,
        tank_id=None,
        quantity_delta=None,
        occurred_at=datetime(2026, 4, 29, 18, 0, tzinfo=UTC),
        note=None,
        recorded_by_user_id=None,
    )

    assert event.id is not None


def test_move_animal_creates_moved_event(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)
    target_tank = Tank(name="Lagoon 25", water_type=WaterType.SALT.value)
    user = db_session.scalar(select(User).where(User.email == "keeper@example.com"))
    moved_at = datetime(2026, 4, 29, 16, 0, tzinfo=UTC)
    db_session.add(target_tank)
    db_session.commit()

    move_event = animal_service.move_animal(
        animal,
        to_tank=target_tank,
        occurred_at=moved_at,
        note="Settled into quarantine.",
        recorded_by_user_id=user.id,
    )

    assert isinstance(move_event, AnimalEvent)
    assert move_event.id is not None
    assert move_event.animal_id == animal.id
    assert move_event.event_type == EventType.MOVED.value
    assert move_event.tank_id == target_tank.id
    assert move_event.quantity_delta is None
    assert move_event.occurred_at.replace(tzinfo=UTC) == moved_at
    assert move_event.note == "Settled into quarantine."
    assert move_event.recorded_by_user_id == user.id
    assert (
        db_session.scalar(select(AnimalEvent).where(AnimalEvent.id == move_event.id)) == move_event
    )


def test_move_animal_normalizes_blank_note(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)
    target_tank = Tank(name="Lagoon 25", water_type=WaterType.SALT.value)
    db_session.add(target_tank)
    db_session.commit()

    move_event = animal_service.move_animal(
        animal,
        to_tank=target_tank,
        occurred_at=datetime(2026, 4, 29, 16, 0, tzinfo=UTC),
        note="",
        recorded_by_user_id=None,
    )

    assert move_event.note is None


def test_move_animal_rejects_tombstoned_animal(app, db_session) -> None:
    _, user = seed_tank_and_user(db_session)
    target_tank = Tank(name="Lagoon 25", water_type=WaterType.SALT.value)
    animal = Animal(
        name="Moe",
        species="Nassarius snail",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add_all([target_tank, animal])
    db_session.flush()
    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.DECEASED.value,
            tank_id=None,
            quantity_delta=-1,
            occurred_at=datetime(2026, 4, 29, 9, 0, tzinfo=UTC),
            recorded_by_user_id=user.id,
        )
    )
    db_session.commit()

    with pytest.raises(ValueError, match="alive"):
        animal_service.move_animal(
            animal,
            to_tank=target_tank,
            occurred_at=datetime(2026, 4, 29, 16, 0, tzinfo=UTC),
            note=None,
            recorded_by_user_id=user.id,
        )

    assert animal_service.current_tank(animal) is None
    assert (
        db_session.scalars(
            select(AnimalEvent).where(
                AnimalEvent.animal_id == animal.id,
                AnimalEvent.event_type == EventType.MOVED.value,
            )
        ).all()
        == []
    )


def test_move_animal_rejects_decommissioned_tank(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)
    target_tank = Tank(
        name="Retired 20",
        water_type=WaterType.SALT.value,
        decommission_date=date(2026, 4, 29),
    )
    db_session.add(target_tank)
    db_session.commit()

    with pytest.raises(ValueError, match="active"):
        animal_service.move_animal(
            animal,
            to_tank=target_tank,
            occurred_at=datetime(2026, 4, 29, 16, 0, tzinfo=UTC),
            note=None,
            recorded_by_user_id=None,
        )

    assert (
        db_session.scalars(
            select(AnimalEvent).where(
                AnimalEvent.animal_id == animal.id,
                AnimalEvent.tank_id == target_tank.id,
            )
        ).all()
        == []
    )


def test_move_animal_does_not_commit(app, db_session, monkeypatch) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)
    target_tank = Tank(name="Lagoon 25", water_type=WaterType.SALT.value)
    db_session.add(target_tank)
    db_session.commit()

    def fail_commit() -> None:
        raise AssertionError("move_animal must not commit")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    move_event = animal_service.move_animal(
        animal,
        to_tank=target_tank,
        occurred_at=datetime(2026, 4, 29, 16, 0, tzinfo=UTC),
        note=None,
        recorded_by_user_id=None,
    )

    assert move_event.id is not None


def test_mark_deceased_partial_group(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)
    user = db_session.scalar(select(User).where(User.email == "keeper@example.com"))
    deceased_at = datetime(2026, 4, 29, 17, 0, tzinfo=UTC)

    deceased_event = animal_service.mark_deceased(
        animal,
        quantity=2,
        occurred_at=deceased_at,
        note="Lost two overnight.",
        recorded_by_user_id=user.id,
    )

    assert isinstance(deceased_event, AnimalEvent)
    assert deceased_event.id is not None
    assert deceased_event.animal_id == animal.id
    assert deceased_event.event_type == EventType.DECEASED.value
    assert deceased_event.tank_id is None
    assert deceased_event.quantity_delta == -2
    assert deceased_event.occurred_at.replace(tzinfo=UTC) == deceased_at
    assert deceased_event.note == "Lost two overnight."
    assert deceased_event.recorded_by_user_id == user.id
    assert animal_service.current_count(animal) == 2
    assert animal_service.is_alive(animal) is True
    assert (
        db_session.scalar(select(AnimalEvent).where(AnimalEvent.id == deceased_event.id))
        == deceased_event
    )


def test_mark_deceased_total_group_tombstones(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    deceased_event = animal_service.mark_deceased(
        animal,
        quantity=4,
        occurred_at=datetime(2026, 4, 29, 17, 0, tzinfo=UTC),
        note="",
        recorded_by_user_id=None,
    )

    assert deceased_event.event_type == EventType.DECEASED.value
    assert deceased_event.tank_id is None
    assert deceased_event.quantity_delta == -4
    assert deceased_event.note is None
    assert animal_service.current_count(animal) == 0
    assert animal_service.is_alive(animal) is False
    assert animal_service.current_tank(animal) is None


def test_mark_deceased_rejects_overcount(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    with pytest.raises(ValueError, match="negative"):
        animal_service.mark_deceased(
            animal,
            quantity=5,
            occurred_at=datetime(2026, 4, 29, 17, 0, tzinfo=UTC),
            note=None,
            recorded_by_user_id=None,
        )

    assert animal_service.current_count(animal) == 4
    assert (
        db_session.scalars(
            select(AnimalEvent).where(
                AnimalEvent.animal_id == animal.id,
                AnimalEvent.occurred_at == datetime(2026, 4, 29, 17, 0, tzinfo=UTC),
            )
        ).all()
        == []
    )


def test_mark_deceased_rejects_non_positive_quantity(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    with pytest.raises(ValueError, match="positive"):
        animal_service.mark_deceased(
            animal,
            quantity=0,
            occurred_at=datetime(2026, 4, 29, 17, 0, tzinfo=UTC),
            note=None,
            recorded_by_user_id=None,
        )


def test_mark_deceased_does_not_commit(app, db_session, monkeypatch) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    def fail_commit() -> None:
        raise AssertionError("mark_deceased must not commit")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    deceased_event = animal_service.mark_deceased(
        animal,
        quantity=1,
        occurred_at=datetime(2026, 4, 29, 17, 0, tzinfo=UTC),
        note=None,
        recorded_by_user_id=None,
    )

    assert deceased_event.id is not None


def test_mark_deceased_locks_animal_before_counting(app, db_session, monkeypatch) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)
    calls: list[str] = []

    def lock_animal_for_update(locked_animal: Animal) -> None:
        assert locked_animal == animal
        calls.append("lock")

    def count_current_animal(counted_animal: Animal) -> int:
        assert counted_animal == animal
        calls.append("count")
        return 4

    monkeypatch.setattr(animal_service, "_lock_animal_for_update", lock_animal_for_update)
    monkeypatch.setattr(animal_service, "current_count", count_current_animal)

    animal_service.mark_deceased(
        animal,
        quantity=1,
        occurred_at=datetime(2026, 4, 29, 17, 0, tzinfo=UTC),
        note=None,
        recorded_by_user_id=None,
    )

    assert calls[:2] == ["lock", "count"]


def test_lock_animal_for_update_uses_postgres_row_lock(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    statement = animal_service._lock_animal_for_update_statement(animal)

    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in compiled
