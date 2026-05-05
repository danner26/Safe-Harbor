"""Animal service - lifecycle-aware livestock operations."""

from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import Select, and_, case, func, inspect, select
from sqlalchemy.sql.selectable import Subquery

import safeharbor.services.upload_service as upload_service
from safeharbor.extensions import db
from safeharbor.models.account import User
from safeharbor.models.animal import Animal
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.models.tank import Tank


def create_animal(
    *,
    name: str | None,
    species: str,
    scientific_name: str | None,
    sex: str | None,
    acquired_quantity: int,
    initial_tank: Tank,
    acquired_at: datetime,
    initial_note: str | None,
    recorded_by_user_id: UUID | None,
    notes: str | None = None,
) -> Animal:
    """Create an animal and its initial acquired lifecycle event.

    The caller is responsible for committing the surrounding transaction.
    """
    animal = Animal(
        name=name,
        species=species,
        scientific_name=scientific_name,
        sex=sex,
        acquired_quantity=acquired_quantity,
        notes=notes or None,
    )
    db.session.add(animal)
    db.session.flush()

    event = AnimalEvent(
        animal_id=animal.id,
        event_type=EventType.ACQUIRED.value,
        tank_id=initial_tank.id,
        quantity_delta=acquired_quantity,
        occurred_at=acquired_at,
        note=initial_note or None,
        recorded_by_user_id=recorded_by_user_id,
    )
    db.session.add(event)
    db.session.flush()

    return animal


def record_event(
    animal: Animal,
    *,
    event_type: EventType | str,
    occurred_at: datetime,
    note: str | None,
    recorded_by_user_id: UUID | None,
    tank_id: UUID | None = None,
    quantity_delta: int | None = None,
) -> AnimalEvent:
    """Record a generic non-lifecycle animal event. Caller commits."""
    try:
        normalized_event_type = EventType(event_type)
    except ValueError as exc:
        raise ValueError("event_type must be health_note or observation.") from exc

    if normalized_event_type not in {EventType.HEALTH_NOTE, EventType.OBSERVATION}:
        raise ValueError("event_type must be health_note or observation.")
    if tank_id is not None:
        raise ValueError("tank_id must be None for health_note and observation events.")
    if quantity_delta is not None:
        raise ValueError("quantity_delta must be None for health_note and observation events.")

    event = AnimalEvent(
        animal_id=_animal_id(animal),
        event_type=normalized_event_type.value,
        tank_id=None,
        quantity_delta=None,
        occurred_at=occurred_at,
        note=note or None,
        recorded_by_user_id=recorded_by_user_id,
    )
    db.session.add(event)
    db.session.flush()
    return event


def delete_if_pristine(animal: Animal) -> None:
    """Hard-delete an animal that only has its initial acquired event. Caller commits."""
    animal_id = _animal_id(animal)
    _lock_animal_for_update(animal)
    events = list(
        db.session.scalars(
            select(AnimalEvent)
            .where(AnimalEvent.animal_id == animal_id)
            .order_by(AnimalEvent.occurred_at.asc(), AnimalEvent.created_at.asc())
            .limit(2)
        )
    )
    if len(events) != 1:
        raise ValueError("Animal must be pristine with exactly one acquired event.")
    if events[0].event_type != EventType.ACQUIRED.value:
        raise ValueError("Animal must have a single acquired event to delete.")
    if events[0].quantity_delta != animal.acquired_quantity:
        raise ValueError("Animal acquired event must match acquired quantity to delete.")

    upload_service.remove_image(entity_type="animals", entity_id=animal.id)
    db.session.delete(animal)
    db.session.flush()


def can_delete_if_pristine(animal: Animal) -> bool:
    """Return whether delete_if_pristine would allow a hard delete without mutating."""
    animal_id = _animal_id(animal)
    events = list(
        db.session.scalars(
            select(AnimalEvent)
            .where(AnimalEvent.animal_id == animal_id)
            .order_by(AnimalEvent.occurred_at.asc(), AnimalEvent.created_at.asc())
            .limit(2)
        )
    )
    return (
        len(events) == 1
        and events[0].event_type == EventType.ACQUIRED.value
        and events[0].quantity_delta == animal.acquired_quantity
    )


def _animal_id(animal: Animal) -> UUID:
    identity = inspect(animal).identity
    if identity is None:
        return animal.id
    return cast(UUID, identity[0])


def _lock_animal_for_update_statement(animal: Animal) -> Select[tuple[UUID]]:
    return select(Animal.id).where(Animal.id == _animal_id(animal)).with_for_update()


def _lock_animal_for_update(animal: Animal) -> None:
    db.session.execute(_lock_animal_for_update_statement(animal)).scalar_one()


def current_count(animal: Animal) -> int:
    """Return the current living quantity for an animal record."""
    animal_id = _animal_id(animal)
    count = db.session.scalar(
        select(func.coalesce(func.sum(AnimalEvent.quantity_delta), 0)).where(
            AnimalEvent.animal_id == animal_id
        )
    )
    return int(count or 0)


def _latest_lifecycle_events_subquery() -> Subquery:
    """Return a subquery with the latest tank-bearing lifecycle event per animal."""
    ranked_events = (
        select(AnimalEvent.animal_id, AnimalEvent.tank_id)
        .where(
            AnimalEvent.event_type.in_(
                [EventType.ACQUIRED.value, EventType.MOVED.value],
            )
        )
        .add_columns(
            func.row_number()
            .over(
                partition_by=AnimalEvent.animal_id,
                order_by=(
                    AnimalEvent.occurred_at.desc(),
                    AnimalEvent.created_at.desc(),
                    AnimalEvent.id.desc(),
                ),
            )
            .label("event_rank")
        )
        .subquery()
    )
    return (
        select(ranked_events.c.animal_id, ranked_events.c.tank_id)
        .where(ranked_events.c.event_rank == 1)
        .subquery()
    )


def current_tank(animal: Animal) -> Tank | None:
    """Return the latest lifecycle tank, or None when no animals remain alive."""
    if not is_alive(animal):
        return None

    animal_id = _animal_id(animal)
    latest_events = _latest_lifecycle_events_subquery()
    latest_tank_id = (
        select(latest_events.c.tank_id)
        .where(latest_events.c.animal_id == animal_id)
        .scalar_subquery()
    )
    return cast(
        "Tank | None",
        db.session.scalar(select(Tank).where(Tank.id == latest_tank_id)),
    )


def animals_on_tank(tank: Tank) -> list[Animal]:
    """Return living animals whose latest lifecycle tank is the given active tank."""
    if tank.decommission_date is not None:
        return []

    latest_events = _latest_lifecycle_events_subquery()
    current_counts = (
        select(
            AnimalEvent.animal_id,
            func.coalesce(func.sum(AnimalEvent.quantity_delta), 0).label("event_delta_total"),
        )
        .group_by(AnimalEvent.animal_id)
        .subquery()
    )

    return list(
        db.session.scalars(
            select(Animal)
            .join(latest_events, latest_events.c.animal_id == Animal.id)
            .outerjoin(current_counts, current_counts.c.animal_id == Animal.id)
            .where(
                latest_events.c.tank_id == tank.id,
                func.coalesce(current_counts.c.event_delta_total, 0) > 0,
            )
            .order_by(Animal.created_at.asc(), Animal.id.asc())
        )
    )


def list_summary() -> tuple[int, int, int]:
    """Return alive, deceased, and occupied-current-tank counts for the animals list."""
    latest_events = _latest_lifecycle_events_subquery()
    current_counts = (
        select(
            AnimalEvent.animal_id,
            func.coalesce(func.sum(AnimalEvent.quantity_delta), 0).label("event_delta_total"),
        )
        .group_by(AnimalEvent.animal_id)
        .subquery()
    )
    current_count = func.coalesce(current_counts.c.event_delta_total, 0)
    alive_condition = current_count > 0
    active_tank_condition = and_(alive_condition, Tank.decommission_date.is_(None))

    row = db.session.execute(
        select(
            func.coalesce(func.sum(case((alive_condition, 1), else_=0)), 0).label("alive_count"),
            func.coalesce(func.sum(case((alive_condition, 0), else_=1)), 0).label("deceased_count"),
            func.count(
                func.distinct(case((active_tank_condition, latest_events.c.tank_id), else_=None))
            ).label("tank_count"),
        )
        .select_from(Animal)
        .outerjoin(current_counts, current_counts.c.animal_id == Animal.id)
        .outerjoin(latest_events, latest_events.c.animal_id == Animal.id)
        .outerjoin(Tank, Tank.id == latest_events.c.tank_id)
    ).one()

    return int(row.alive_count or 0), int(row.deceased_count or 0), int(row.tank_count or 0)


def is_alive(animal: Animal) -> bool:
    """Return whether any quantity remains alive."""
    return current_count(animal) > 0


def move_animal(
    animal: Animal,
    *,
    to_tank: Tank,
    occurred_at: datetime,
    note: str | None,
    recorded_by_user_id: UUID | None,
) -> AnimalEvent:
    """Record a move lifecycle event. Caller commits."""
    _lock_animal_for_update(animal)
    if not is_alive(animal):
        raise ValueError("Animal must be alive to move.")
    if to_tank.decommission_date is not None:
        raise ValueError("Destination tank must be active.")

    event = AnimalEvent(
        animal_id=_animal_id(animal),
        event_type=EventType.MOVED.value,
        tank_id=to_tank.id,
        quantity_delta=None,
        occurred_at=occurred_at,
        note=note or None,
        recorded_by_user_id=recorded_by_user_id,
    )
    db.session.add(event)
    db.session.flush()
    return event


def mark_deceased(
    animal: Animal,
    *,
    quantity: int,
    occurred_at: datetime,
    note: str | None,
    recorded_by_user_id: UUID | None,
) -> AnimalEvent:
    """Record a deceased lifecycle event. Caller commits."""
    if quantity <= 0:
        raise ValueError("Quantity must be a positive integer.")
    _lock_animal_for_update(animal)
    if current_count(animal) - quantity < 0:
        raise ValueError("Deceased quantity cannot make current count negative.")

    event = AnimalEvent(
        animal_id=_animal_id(animal),
        event_type=EventType.DECEASED.value,
        tank_id=None,
        quantity_delta=-quantity,
        occurred_at=occurred_at,
        note=note or None,
        recorded_by_user_id=recorded_by_user_id,
    )
    db.session.add(event)
    db.session.flush()
    return event


def lifecycle_for(animal: Animal) -> list[AnimalEvent]:
    """Return lifecycle events ordered oldest to newest."""
    animal_id = _animal_id(animal)
    return list(
        db.session.scalars(
            select(AnimalEvent)
            .where(AnimalEvent.animal_id == animal_id)
            .order_by(AnimalEvent.occurred_at.asc(), AnimalEvent.created_at.asc())
        )
    )


def lifecycle_rows(animal: Animal) -> list[dict[str, object]]:
    """Return timeline display rows with recorder names resolved in one batch."""
    events = lifecycle_for(animal)
    recorder_ids = {
        event.recorded_by_user_id for event in events if event.recorded_by_user_id is not None
    }
    recorders = (
        db.session.scalars(select(User).where(User.id.in_(recorder_ids))).all()
        if recorder_ids
        else []
    )
    recorder_by_id = {user.id: user for user in recorders}

    rows: list[dict[str, object]] = []
    for event in events:
        recorder = (
            recorder_by_id.get(event.recorded_by_user_id)
            if event.recorded_by_user_id is not None
            else None
        )
        rows.append(
            {
                "event": event,
                "event_type": event.event_type,
                "occurred_at": event.occurred_at,
                "tank_id": event.tank_id,
                "quantity_delta": event.quantity_delta,
                "note": event.note,
                "logged_by_display": f"logged by {recorder.display_username()}"
                if recorder is not None
                else None,
            }
        )

    return rows
