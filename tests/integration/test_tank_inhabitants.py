"""GET /tanks/<id> - inhabitants partial integration."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from flask import url_for


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email=f"viewer-{uuid4()}@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_tank(db_session: Any, name: str = "Lagoon") -> Any:
    from safeharbor.models.tank import Tank

    tank = Tank(name=name, water_type="salt")
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_animal(
    db_session: Any,
    *,
    tank: Any,
    name: str | None,
    species: str = "Ocellaris clownfish",
    deceased: bool = False,
    image_path: str | None = None,
) -> Any:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType

    animal = Animal(name=name, species=species, acquired_quantity=1, image_path=image_path)
    db_session.add(animal)
    db_session.flush()
    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.ACQUIRED.value,
            tank_id=tank.id,
            quantity_delta=1,
            occurred_at=datetime(2026, 4, 26, 12, 30, tzinfo=UTC),
        )
    )
    if deceased:
        db_session.add(
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.DECEASED.value,
                tank_id=None,
                quantity_delta=-1,
                occurred_at=datetime(2026, 4, 27, 8, 15, tzinfo=UTC),
            )
        )
    db_session.commit()
    return animal


def test_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    resp = client.get(f"/tanks/{uuid4()}", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_alive_animals_visible(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank, name="Mango")

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Mango" in body
    assert f'href="/animals/{animal.id}"' in body
    assert "No animals on this tank yet" not in body


def test_tombstoned_excluded(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    _seed_animal(db_session, tank=tank, name="Mango")
    _seed_animal(db_session, tank=tank, name="Ghost", deceased=True)

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Mango" in body
    assert "Ghost" not in body


def test_empty_state_links_to_new_with_tank_param(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "No animals on this tank yet — Add one →" in body
    assert f'href="/animals/new?tank={tank.id}"' in body


def test_inhabitant_thumbnail_renders_when_image_set(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(
        db_session,
        tank=tank,
        name="Mango",
        image_path="animals/mango.webp",
    )

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert f'src="{url_for("animals.serve_image", animal_id=animal.id)}"' in body
    assert 'alt="Mango photo"' in body
    assert "linear-gradient(135deg, var(--surface-2), var(--border))" not in body


def test_inhabitant_placeholder_renders_when_image_null(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank, name="Mango", image_path=None)

    resp = client.get(f"/tanks/{tank.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "linear-gradient(135deg, var(--surface-2), var(--border))" in body
    assert url_for("animals.serve_image", animal_id=animal.id) not in body
