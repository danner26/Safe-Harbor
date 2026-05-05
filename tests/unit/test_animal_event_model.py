"""AnimalEvent model - lifecycle event field shapes and CHECK constraints."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from safeharbor.models import AnimalEvent as ExportedAnimalEvent
from safeharbor.models import EventType as ExportedEventType
from safeharbor.models.animal import Animal
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.models.tank import Tank


def _seed_animal(db_session) -> Animal:
    animal = Animal(species="Amphiprion ocellaris", acquired_quantity=2)
    db_session.add(animal)
    db_session.commit()
    return animal


def _seed_tank(db_session) -> Tank:
    tank = Tank(name="Reef 90", water_type="salt")
    db_session.add(tank)
    db_session.commit()
    return tank


def test_event_type_enum_values() -> None:
    assert EventType.ACQUIRED.value == "acquired"
    assert EventType.MOVED.value == "moved"
    assert EventType.DECEASED.value == "deceased"
    assert EventType.HEALTH_NOTE.value == "health_note"
    assert EventType.OBSERVATION.value == "observation"


def test_animal_event_is_exported_from_models_package() -> None:
    assert ExportedAnimalEvent is AnimalEvent
    assert ExportedEventType is EventType


def test_animal_event_table_has_specified_columns_only(app, db_session) -> None:
    inspector = inspect(db_session.bind)
    columns = [column["name"] for column in inspector.get_columns("animal_events")]
    assert columns == [
        "id",
        "animal_id",
        "event_type",
        "tank_id",
        "quantity_delta",
        "occurred_at",
        "note",
        "recorded_by_user_id",
        "created_at",
    ]


def test_animal_event_foreign_keys_include_animal_delete_cascade(app, db_session) -> None:
    inspector = inspect(db_session.bind)
    foreign_keys = {
        fk["constrained_columns"][0]: fk for fk in inspector.get_foreign_keys("animal_events")
    }

    assert foreign_keys["animal_id"]["referred_table"] == "animals"
    assert foreign_keys["animal_id"]["options"]["ondelete"] == "CASCADE"
    assert foreign_keys["tank_id"]["referred_table"] == "tanks"
    assert foreign_keys["recorded_by_user_id"]["referred_table"] == "users"


def test_animal_event_can_be_persisted_with_required_fields(app, db_session) -> None:
    animal = _seed_animal(db_session)
    event = AnimalEvent(
        animal_id=animal.id,
        event_type=EventType.OBSERVATION.value,
        occurred_at=datetime.now(UTC),
    )
    db_session.add(event)
    db_session.commit()

    assert isinstance(event.id, UUID)
    assert event.tank_id is None
    assert event.quantity_delta is None
    assert event.note is None
    assert event.recorded_by_user_id is None
    assert event.created_at is not None


@pytest.mark.parametrize(
    ("event_type", "tank_needed", "quantity_delta"),
    [
        (EventType.ACQUIRED.value, True, 3),
        (EventType.MOVED.value, True, None),
        (EventType.DECEASED.value, False, -1),
        (EventType.HEALTH_NOTE.value, False, None),
        (EventType.OBSERVATION.value, False, None),
    ],
)
def test_animal_event_valid_lifecycle_rules(
    app,
    db_session,
    event_type: str,
    tank_needed: bool,
    quantity_delta: int | None,
) -> None:
    animal = _seed_animal(db_session)
    tank = _seed_tank(db_session) if tank_needed else None
    event = AnimalEvent(
        animal_id=animal.id,
        event_type=event_type,
        tank_id=tank.id if tank is not None else None,
        quantity_delta=quantity_delta,
        occurred_at=datetime.now(UTC),
        note="Lifecycle note.",
    )
    db_session.add(event)
    db_session.commit()

    fetched = db_session.scalar(select(AnimalEvent).where(AnimalEvent.id == event.id))
    assert fetched is not None
    assert fetched.event_type == event_type


@pytest.mark.parametrize(
    ("event_type", "tank_needed", "quantity_delta"),
    [
        (EventType.ACQUIRED.value, False, 1),
        (EventType.ACQUIRED.value, True, None),
        (EventType.ACQUIRED.value, True, 0),
        (EventType.MOVED.value, False, None),
        (EventType.MOVED.value, True, 1),
        (EventType.DECEASED.value, True, -1),
        (EventType.DECEASED.value, False, None),
        (EventType.DECEASED.value, False, 0),
        (EventType.HEALTH_NOTE.value, True, None),
        (EventType.HEALTH_NOTE.value, False, 1),
        (EventType.OBSERVATION.value, True, None),
        (EventType.OBSERVATION.value, False, -1),
        ("escaped", False, None),
    ],
)
def test_animal_event_lifecycle_rule_check_constraint(
    app,
    db_session,
    event_type: str,
    tank_needed: bool,
    quantity_delta: int | None,
) -> None:
    animal = _seed_animal(db_session)
    tank = _seed_tank(db_session) if tank_needed else None
    event = AnimalEvent(
        animal_id=animal.id,
        event_type=event_type,
        tank_id=tank.id if tank is not None else None,
        quantity_delta=quantity_delta,
        occurred_at=datetime.now(UTC),
    )
    db_session.add(event)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_animal_event_animal_fk_cascades_on_delete(app, db_session) -> None:
    animal = _seed_animal(db_session)
    event = AnimalEvent(
        animal_id=animal.id,
        event_type=EventType.OBSERVATION.value,
        occurred_at=datetime.now(UTC),
    )
    db_session.add(event)
    db_session.commit()
    event_id = event.id

    db_session.delete(animal)
    db_session.commit()

    assert db_session.scalar(select(AnimalEvent).where(AnimalEvent.id == event_id)) is None
