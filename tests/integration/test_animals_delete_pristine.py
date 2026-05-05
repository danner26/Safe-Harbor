"""POST /animals/<id>/delete - pristine-only animal delete flow."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from flask import Flask
from sqlalchemy import select, text


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

    if db_session.bind.dialect.name == "sqlite":
        db_session.execute(text("PRAGMA foreign_keys=ON"))

    tank = Tank(name=name, water_type=WaterType.SALT.value)
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_animal(
    db_session: Any,
    *,
    tank: Any,
    quantity: int = 1,
) -> Any:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType

    animal = Animal(
        name="Mabel",
        species="Ocellaris clownfish",
        scientific_name="Amphiprion ocellaris",
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


def _add_note_event(db_session: Any, animal: Any) -> None:
    from safeharbor.models.animal_event import AnimalEvent, EventType

    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.HEALTH_NOTE.value,
            tank_id=None,
            quantity_delta=None,
            occurred_at=datetime(2026, 4, 27, 8, 15, tzinfo=UTC),
            note="Eating well.",
        )
    )
    db_session.commit()


def _csrf_token(response_data: bytes) -> str:
    match = re.search(
        rb'name="csrf_token" type="hidden" value="([^"]+)"',
        response_data,
    )
    assert match is not None
    return match.group(1).decode()


def test_unauthenticated_redirects_to_login(client: Any) -> None:
    resp = client.post(f"/animals/{uuid4()}/delete", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_pristine_delete_succeeds(client: Any, db_session: Any) -> None:
    from safeharbor.models.animal import Animal

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)
    animal_id = animal.id

    resp = client.post(f"/animals/{animal_id}/delete", follow_redirects=False)

    assert resp.status_code == 302
    assert resp.location == "/animals"
    assert db_session.get(Animal, animal_id) is None


def test_non_pristine_delete_returns_form_error(client: Any, db_session: Any) -> None:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)
    animal_id = animal.id
    _add_note_event(db_session, animal)

    resp = client.post(f"/animals/{animal_id}/delete", follow_redirects=True)

    assert resp.status_code == 200
    assert b"Animal must be pristine with exactly one acquired event." in resp.data
    assert db_session.get(Animal, animal_id) is not None
    events = list(
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == animal_id)).all()
    )
    assert len(events) == 2


def test_pristine_delete_cascades_acquired_event(client: Any, db_session: Any) -> None:
    from safeharbor.models.animal_event import AnimalEvent

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)
    animal_id = animal.id

    resp = client.post(f"/animals/{animal_id}/delete", follow_redirects=False)

    assert resp.status_code == 302
    events = list(
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == animal_id)).all()
    )
    assert events == []


def test_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.post(f"/animals/{animal.id}/delete", follow_redirects=False)

    assert resp.status_code == 400


def test_csrf_accepts_valid_token(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)
    form_resp = client.get(f"/animals/{animal.id}")

    resp = client.post(
        f"/animals/{animal.id}/delete",
        data={"csrf_token": _csrf_token(form_resp.data)},
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location == "/animals"
