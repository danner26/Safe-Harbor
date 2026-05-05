"""Visual animal fixtures are marked and deleted by marker only."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select


def _seed_tank(db_session: Any) -> Any:
    from safeharbor.models.tank import Tank, WaterType

    tank = Tank(name="Real Reef", water_type=WaterType.SALT.value)
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_animal(
    db_session: Any,
    *,
    tank: Any,
    species: str,
    notes: str | None,
) -> Any:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType

    animal = Animal(
        name="Real livestock",
        species=species,
        acquired_quantity=1,
        notes=notes,
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
        )
    )
    db_session.commit()
    return animal


def test_delete_visual_animals_only_removes_marked(app: Any, db_session: Any) -> None:
    from safeharbor.blueprints.dev.views import _FIXTURE_NOTE_PREFIX, _delete_visual_animals
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent

    tank = _seed_tank(db_session)
    marked = _seed_animal(
        db_session,
        tank=tank,
        species="Ocellaris clownfish",
        notes=f"{_FIXTURE_NOTE_PREFIX} list scene",
    )
    unmarked = _seed_animal(
        db_session,
        tank=tank,
        species="Ocellaris clownfish",
        notes="real keeper note",
    )

    _delete_visual_animals()
    db_session.commit()

    assert db_session.get(Animal, marked.id) is None
    assert db_session.get(Animal, unmarked.id) is not None
    assert (
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == marked.id)).all()
        == []
    )
    assert db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == unmarked.id)).all()


def test_delete_visual_animals_preserves_real_user_data(client: Any, db_session: Any) -> None:
    from safeharbor.blueprints.dev.views import _FIXTURE_NOTE_PREFIX
    from safeharbor.models.animal import Animal

    tank = _seed_tank(db_session)
    real_animal = _seed_animal(
        db_session,
        tank=tank,
        species="Ocellaris clownfish",
        notes="real user livestock, not a fixture",
    )

    resp = client.get("/__test/visual-fixtures/seed-animals-list")

    assert resp.status_code == 302
    assert db_session.get(Animal, real_animal.id) is not None
    fixture_animals = db_session.scalars(select(Animal).where(Animal.id != real_animal.id)).all()
    assert fixture_animals
    assert all(
        animal.notes is not None and animal.notes.startswith(_FIXTURE_NOTE_PREFIX)
        for animal in fixture_animals
    )
