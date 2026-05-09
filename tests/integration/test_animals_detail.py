"""GET /animals/<id> - animal detail view."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from flask import url_for


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


def _seed_tank(db_session: Any, *, name: str = "Reef 90") -> Any:
    from safeharbor.models.tank import Tank, WaterType

    tank = Tank(name=name, water_type=WaterType.SALT.value)
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_animal(
    db_session: Any,
    *,
    tank: Any,
    name: str | None = "Mabel",
    species: str = "Ocellaris clownfish",
    scientific_name: str | None = "Amphiprion ocellaris",
    quantity: int = 1,
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
            occurred_at=datetime(2026, 4, 26, 12, 30, tzinfo=UTC),
            note="Acquired from local breeder.",
        )
    )
    db_session.commit()
    return animal


def _add_event(
    db_session: Any,
    animal: Any,
    *,
    event_type: str,
    occurred_at: datetime,
    tank: Any | None = None,
    quantity_delta: int | None = None,
    note: str | None = None,
) -> Any:
    from safeharbor.models.animal_event import AnimalEvent

    event = AnimalEvent(
        animal_id=animal.id,
        event_type=event_type,
        tank_id=tank.id if tank is not None else None,
        quantity_delta=quantity_delta,
        occurred_at=occurred_at,
        note=note,
    )
    db_session.add(event)
    db_session.commit()
    return event


def test_unauthenticated_redirects(client: Any, configured_user) -> None:
    resp = client.get(f"/animals/{uuid4()}", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_404_unknown_id(client: Any, db_session: Any) -> None:
    _login(client, db_session)

    resp = client.get(f"/animals/{uuid4()}")

    assert resp.status_code == 404


def test_detail_renders_hero_and_timeline_ascending(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    lagoon = _seed_tank(db_session, name="Lagoon 40")
    animal = _seed_animal(db_session, tank=reef, quantity=2)
    _add_event(
        db_session,
        animal,
        event_type="observation",
        occurred_at=datetime(2026, 4, 28, 9, 0, tzinfo=UTC),
        note="Hosting the hammer coral.",
    )
    _add_event(
        db_session,
        animal,
        event_type="moved",
        tank=lagoon,
        occurred_at=datetime(2026, 4, 27, 8, 15, tzinfo=UTC),
        note="Moved after quarantine.",
    )

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Mabel" in body
    assert "Ocellaris clownfish" in body
    assert "Amphiprion ocellaris" in body
    assert "Alive" in body
    assert "Lagoon 40" in body
    assert "2 total" in body
    assert body.index("2026-04-26") < body.index("2026-04-27") < body.index("2026-04-28")
    assert "Acquired" in body
    assert "Moved" in body
    assert "Observation" in body
    assert "Moved after quarantine." in body


def test_hero_photo_renders_when_image_path_set(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank, name="Mabel")
    animal.image_path = "animals/mabel.webp"
    db_session.commit()

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert f'src="{url_for("animals.serve_image", animal_id=animal.id)}"' in body
    assert 'alt="Mabel photo"' in body
    assert "linear-gradient(135deg, var(--surface-2), var(--border))" not in body


def test_placeholder_renders_when_image_path_null(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "linear-gradient(135deg, var(--surface-2), var(--border))" in body
    assert url_for("animals.serve_image", animal_id=animal.id) not in body


def test_alive_animal_actions_visible(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert f'href="{url_for("animals.edit_animal", animal_id=animal.id)}"' in body
    assert 'data-action="edit"' in body
    assert 'data-action="move"' in body
    assert 'data-action="mark-deceased"' in body
    assert 'data-action="add-note"' in body


def test_tombstoned_animal_hides_move_and_deceased(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)
    _add_event(
        db_session,
        animal,
        event_type="deceased",
        occurred_at=datetime(2026, 4, 27, 8, 15, tzinfo=UTC),
        quantity_delta=-1,
        note="Found deceased.",
    )

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Deceased" in body
    assert "Tombstoned" in body
    assert 'data-action="edit"' in body
    assert 'data-action="move"' not in body
    assert 'data-action="mark-deceased"' not in body
    assert 'data-action="add-note"' in body


def test_pristine_animal_shows_delete(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    assert 'data-action="delete"' in resp.data.decode()


def test_non_pristine_animal_hides_delete(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)
    _add_event(
        db_session,
        animal,
        event_type="health_note",
        occurred_at=datetime(2026, 4, 27, 8, 15, tzinfo=UTC),
        note="Eating well.",
    )

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    assert 'data-action="delete"' not in resp.data.decode()
