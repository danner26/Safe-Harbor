"""Historical tank snapshots for animal service writers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from safeharbor.models.account import User
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.models.tank import Tank, WaterType
from safeharbor.services import animal_service


def _seed_tank(db_session: Any, *, name: str) -> Tank:
    tank = Tank(name=name, water_type=WaterType.SALT.value)
    db_session.add(tank)
    db_session.flush()
    return tank


def _seed_user(db_session: Any) -> User:
    user = User(email=f"keeper-{uuid4()}@example.com", password_hash="hash")
    db_session.add(user)
    db_session.flush()
    return user


def _events_for(db_session: Any, animal_id: object) -> list[AnimalEvent]:
    return list(
        db_session.scalars(
            select(AnimalEvent)
            .where(AnimalEvent.animal_id == animal_id)
            .order_by(AnimalEvent.occurred_at.asc(), AnimalEvent.created_at.asc())
        )
    )


def test_current_tank_id_for_returns_most_recent_pinned(db_session: Any) -> None:
    tank_a = _seed_tank(db_session, name="Reef 90")
    tank_b = _seed_tank(db_session, name="Lagoon 40")
    user = _seed_user(db_session)
    acquired_at = datetime(2026, 4, 1, 12, 0, tzinfo=UTC)
    between_a_and_b = datetime(2026, 4, 2, 12, 0, tzinfo=UTC)
    moved_at = datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    after_b = datetime(2026, 4, 4, 12, 0, tzinfo=UTC)
    animal = animal_service.create_animal(
        name="Mabel",
        species="Ocellaris clownfish",
        scientific_name=None,
        sex=None,
        acquired_quantity=2,
        initial_tank=tank_a,
        acquired_at=acquired_at,
        initial_note=None,
        recorded_by_user_id=user.id,
    )
    animal_service.move_animal(
        animal,
        to_tank=tank_b,
        occurred_at=moved_at,
        note=None,
        recorded_by_user_id=user.id,
    )

    assert animal_service._current_tank_id_for(animal.id, between_a_and_b) == tank_a.id
    assert animal_service._current_tank_id_for(animal.id, after_b) == tank_b.id


def test_current_tank_id_for_raises_when_no_history(db_session: Any) -> None:
    with pytest.raises(ValueError, match="has no tank history"):
        animal_service._current_tank_id_for(uuid4(), datetime(2026, 4, 1, 12, 0, tzinfo=UTC))


def test_writer_call_sites_stamp_tank_id_at_event(db_session: Any) -> None:
    tank_a = _seed_tank(db_session, name="Reef 90")
    tank_b = _seed_tank(db_session, name="Lagoon 40")
    user = _seed_user(db_session)
    animal = animal_service.create_animal(
        name="Mabel",
        species="Ocellaris clownfish",
        scientific_name=None,
        sex=None,
        acquired_quantity=2,
        initial_tank=tank_a,
        acquired_at=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),
        initial_note="Acquired from local breeder.",
        recorded_by_user_id=user.id,
    )
    animal_service.record_event(
        animal,
        event_type=EventType.OBSERVATION,
        occurred_at=datetime(2026, 4, 2, 12, 0, tzinfo=UTC),
        note="Eating well.",
        recorded_by_user_id=user.id,
    )
    animal_service.move_animal(
        animal,
        to_tank=tank_b,
        occurred_at=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
        note="Moved after quarantine.",
        recorded_by_user_id=user.id,
    )
    animal_service.record_event(
        animal,
        event_type=EventType.HEALTH_NOTE,
        occurred_at=datetime(2026, 4, 4, 12, 0, tzinfo=UTC),
        note="Settled in.",
        recorded_by_user_id=user.id,
    )
    animal_service.mark_deceased(
        animal,
        quantity=1,
        occurred_at=datetime(2026, 4, 5, 12, 0, tzinfo=UTC),
        note="Found deceased.",
        recorded_by_user_id=user.id,
    )

    events = _events_for(db_session, animal.id)

    assert [event.event_type for event in events] == [
        EventType.ACQUIRED.value,
        EventType.OBSERVATION.value,
        EventType.MOVED.value,
        EventType.HEALTH_NOTE.value,
        EventType.DECEASED.value,
    ]
    acquired, observation, moved, health_note, deceased = events
    assert acquired.tank_id == tank_a.id
    assert acquired.tank_id_at_event == tank_a.id
    assert observation.tank_id is None
    assert observation.tank_id_at_event == tank_a.id
    assert moved.tank_id == tank_b.id
    assert moved.tank_id_at_event == tank_b.id
    assert health_note.tank_id is None
    assert health_note.tank_id_at_event == tank_b.id
    assert deceased.tank_id is None
    assert deceased.tank_id_at_event == tank_b.id
