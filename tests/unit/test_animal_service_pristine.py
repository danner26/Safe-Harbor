"""Animal service pristine deletion tests."""

from __future__ import annotations

import warnings
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SAWarning

from safeharbor.extensions import db
from safeharbor.models.animal import Animal
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.services import animal_service
from safeharbor.services.animal_service import create_animal
from tests.unit.animal_test_helpers import app as app
from tests.unit.animal_test_helpers import seed_animal_with_events, seed_tank_and_user


def test_delete_if_pristine_deletes_animal_with_single_acquired_event(app, db_session) -> None:
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
    event_id = db_session.scalar(select(AnimalEvent.id).where(AnimalEvent.animal_id == animal.id))

    with warnings.catch_warnings():
        warnings.simplefilter("error", SAWarning)
        animal_service.delete_if_pristine(animal)

    assert db_session.get(Animal, animal.id) is None
    if db_session.get_bind().dialect.name != "sqlite":
        assert db_session.get(AnimalEvent, event_id) is None


def test_delete_if_pristine_relies_on_animal_cascade(app, db_session, monkeypatch) -> None:
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
    deleted: list[object] = []
    original_delete = db.session.delete

    def spy_delete(instance: object) -> None:
        deleted.append(instance)
        original_delete(instance)

    monkeypatch.setattr(db.session, "delete", spy_delete)

    animal_service.delete_if_pristine(animal)

    assert deleted == [animal]


def test_delete_if_pristine_locks_animal_before_event_check(app, db_session, monkeypatch) -> None:
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
    calls: list[str] = []
    original_scalars = db.session.scalars

    def spy_lock(_locked_animal):
        calls.append("lock")

    def spy_scalars(statement, *args, **kwargs):
        calls.append("events")
        return original_scalars(statement, *args, **kwargs)

    monkeypatch.setattr(animal_service, "_lock_animal_for_update", spy_lock)
    monkeypatch.setattr(db.session, "scalars", spy_scalars)

    animal_service.delete_if_pristine(animal)

    assert calls[:2] == ["lock", "events"]


def test_delete_if_pristine_rejects_animal_with_multiple_events(app, db_session) -> None:
    animal, _, _, _ = seed_animal_with_events(db_session)

    with pytest.raises(ValueError, match="pristine"):
        animal_service.delete_if_pristine(animal)

    assert db_session.get(Animal, animal.id) == animal
    assert len(animal_service.lifecycle_for(animal)) == 4


def test_delete_if_pristine_rejects_single_non_acquired_event(app, db_session) -> None:
    animal = Animal(
        name="Tiny",
        species="Neon goby",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
    )
    db_session.add(animal)
    db_session.flush()
    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.OBSERVATION.value,
            tank_id=None,
            quantity_delta=None,
            occurred_at=datetime(2026, 4, 29, 14, 30, tzinfo=UTC),
        )
    )
    db_session.commit()

    with pytest.raises(ValueError, match="acquired"):
        animal_service.delete_if_pristine(animal)

    assert db_session.get(Animal, animal.id) == animal


def test_delete_if_pristine_does_not_commit(app, db_session, monkeypatch) -> None:
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

    def fail_commit() -> None:
        raise AssertionError("delete_if_pristine must not commit")

    monkeypatch.setattr(db.session, "commit", fail_commit)

    animal_service.delete_if_pristine(animal)

    assert db_session.get(Animal, animal.id) is None
