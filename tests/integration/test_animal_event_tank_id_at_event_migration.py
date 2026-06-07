"""Migration backfill coverage for AnimalEvent.tank_id_at_event."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, text

from safeharbor.models.animal import Animal
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.models.tank import Tank, WaterType


def test_backfill_populates_pinned_and_nonpinned_events(db_session: Any) -> None:
    tank_a = Tank(name="Tank A", water_type=WaterType.FRESH.value)
    tank_b = Tank(name="Tank B", water_type=WaterType.FRESH.value)
    animal = Animal(
        name="Mabel",
        species="Ocellaris clownfish",
        acquired_quantity=2,
    )
    db_session.add_all([tank_a, tank_b, animal])
    db_session.flush()

    occurred_at = datetime(2026, 6, 6, 12, 0, tzinfo=UTC)
    created_at = datetime(2026, 6, 6, 12, 30, tzinfo=UTC)
    db_session.add_all(
        [
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=tank_a.id,
                tank_id_at_event=None,
                quantity_delta=2,
                occurred_at=occurred_at,
                created_at=created_at,
            ),
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.HEALTH_NOTE.value,
                tank_id=None,
                tank_id_at_event=None,
                quantity_delta=None,
                occurred_at=occurred_at + timedelta(hours=1),
                created_at=created_at + timedelta(hours=1),
            ),
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.MOVED.value,
                tank_id=tank_b.id,
                tank_id_at_event=None,
                quantity_delta=None,
                occurred_at=occurred_at + timedelta(hours=2),
                created_at=created_at + timedelta(hours=2),
            ),
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.HEALTH_NOTE.value,
                tank_id=None,
                tank_id_at_event=None,
                quantity_delta=None,
                occurred_at=occurred_at + timedelta(hours=3),
                created_at=created_at + timedelta(hours=3),
            ),
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.DECEASED.value,
                tank_id=None,
                tank_id_at_event=None,
                quantity_delta=-1,
                occurred_at=occurred_at + timedelta(hours=4),
                created_at=created_at + timedelta(hours=4),
            ),
        ]
    )
    db_session.flush()

    db_session.execute(
        text("UPDATE animal_events SET tank_id_at_event = tank_id WHERE tank_id IS NOT NULL")
    )
    db_session.execute(
        text(
            """
        UPDATE animal_events e SET tank_id_at_event = (
          SELECT p.tank_id FROM animal_events p
          WHERE p.animal_id = e.animal_id
            AND p.tank_id IS NOT NULL
            AND (
              p.occurred_at < e.occurred_at
              OR (
                p.occurred_at = e.occurred_at
                AND (
                  p.created_at < e.created_at
                  OR (p.created_at = e.created_at AND p.id <= e.id)
                )
              )
            )
          ORDER BY p.occurred_at DESC, p.created_at DESC, p.id DESC
          LIMIT 1
        )
        WHERE e.tank_id IS NULL
        """
        )
    )

    events = db_session.scalars(
        select(AnimalEvent)
        .where(AnimalEvent.animal_id == animal.id)
        .order_by(AnimalEvent.occurred_at.asc())
    ).all()

    assert [event.tank_id_at_event for event in events] == [
        tank_a.id,
        tank_a.id,
        tank_b.id,
        tank_b.id,
        tank_b.id,
    ]
