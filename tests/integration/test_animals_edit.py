"""GET + POST /animals/<id>/edit - animal edit flow."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from flask import Flask
from werkzeug.datastructures import MultiDict


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
    sex: str | None = "female",
    quantity: int = 2,
    notes: str | None = "Bonded pair.",
) -> Any:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType

    animal = Animal(
        name=name,
        species=species,
        scientific_name=scientific_name,
        sex=sex,
        acquired_quantity=quantity,
        notes=notes,
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


def _edit_payload(**overrides: Any) -> dict[str, str]:
    payload = {
        "name": "Marigold",
        "species": "Yellow tang",
        "scientific_name": "Zebrasoma flavescens",
        "sex": "unknown",
        "notes": "Grazes all afternoon.",
        "submit": "Save",
    }
    payload.update({key: str(value) for key, value in overrides.items()})
    return payload


def test_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    resp = client.get(f"/animals/{uuid4()}/edit", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_get_renders_edit_form_with_add_only_fields_hidden(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.get(f"/animals/{animal.id}/edit")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert "Edit animal" in body
    assert f'action="/animals/{animal.id}/edit"' in body
    assert 'name="csrf_token"' in body
    assert 'name="name"' in body
    assert 'value="Mabel"' in body
    assert 'name="species"' in body
    assert 'value="Ocellaris clownfish"' in body
    assert 'name="scientific_name"' in body
    assert 'name="sex"' in body
    assert 'name="notes"' in body
    assert re.search(r'name="acquired_quantity"', body) is None
    assert re.search(r'name="tank_id"', body) is None
    assert re.search(r'name="acquired_at"', body) is None
    assert "Initial note" not in body


def test_post_updates_descriptive_fields_only(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.post(
        f"/animals/{animal.id}/edit",
        data=_edit_payload(),
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location == f"/animals/{animal.id}"
    db_session.refresh(animal)
    assert animal.name == "Marigold"
    assert animal.species == "Yellow tang"
    assert animal.scientific_name == "Zebrasoma flavescens"
    assert animal.sex == "unknown"
    assert animal.notes == "Grazes all afternoon."
    assert animal.acquired_quantity == 2

    events = list(
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == animal.id)).all()
    )
    assert len(events) == 1
    assert events[0].tank_id == tank.id
    assert events[0].quantity_delta == 2


def test_post_rejects_quantity_change_attempt(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.post(
        f"/animals/{animal.id}/edit",
        data=_edit_payload(acquired_quantity="9"),
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert b"Acquisition fields cannot be changed here." in resp.data
    db_session.refresh(animal)
    assert animal.name == "Mabel"
    assert animal.acquired_quantity == 2


def test_post_rejects_tank_change_attempt(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent

    _login(client, db_session)
    original_tank = _seed_tank(db_session)
    other_tank = _seed_tank(db_session, name="Lagoon 40")
    animal = _seed_animal(db_session, tank=original_tank)

    resp = client.post(
        f"/animals/{animal.id}/edit",
        data=_edit_payload(tank_id=other_tank.id),
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert b"Acquisition fields cannot be changed here." in resp.data
    db_session.refresh(animal)
    assert animal.name == "Mabel"

    events = list(
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == animal.id)).all()
    )
    assert len(events) == 1
    assert events[0].tank_id == original_tank.id


def test_post_rejects_acquired_at_change_attempt(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.post(
        f"/animals/{animal.id}/edit",
        data=_edit_payload(acquired_at="2026-04-29T09:00"),
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert b"Acquisition fields cannot be changed here." in resp.data
    db_session.refresh(animal)
    assert animal.name == "Mabel"


def test_edit_with_forbidden_fields_rejects_and_does_not_mutate(
    client: Any,
    db_session: Any,
) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent

    _login(client, db_session)
    original_tank = _seed_tank(db_session)
    other_tank = _seed_tank(db_session, name="Lagoon 40")
    animal = _seed_animal(db_session, tank=original_tank)

    resp = client.post(
        f"/animals/{animal.id}/edit",
        data=_edit_payload(
            acquired_quantity="9",
            tank_id=other_tank.id,
            acquired_at="2026-04-29T09:00",
        ),
        follow_redirects=False,
    )

    assert resp.status_code == 200
    assert resp.data.count(b"Acquisition fields cannot be changed here.") == 1
    db_session.refresh(animal)
    assert animal.name == "Mabel"
    assert animal.species == "Ocellaris clownfish"
    assert animal.scientific_name == "Amphiprion ocellaris"
    assert animal.sex == "female"
    assert animal.notes == "Bonded pair."
    assert animal.acquired_quantity == 2

    events = list(
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == animal.id)).all()
    )
    assert len(events) == 1
    assert events[0].tank_id == original_tank.id
    assert events[0].quantity_delta == 2


def test_animal_edit_form_validate_does_not_duplicate_forbidden_field_error(
    app: Flask,
) -> None:
    from safeharbor.blueprints.animals.forms import AnimalEditForm

    formdata = MultiDict(
        {
            "name": "Marigold",
            "species": "Yellow tang",
            "scientific_name": "Zebrasoma flavescens",
            "sex": "unknown",
            "notes": "Grazes all afternoon.",
        }
    )
    with app.test_request_context("/animals/edit", method="POST"):
        form = AnimalEditForm(
            formdata=formdata,
            forbidden_field_names={"acquired_quantity", "tank_id"},
        )

        assert form.validate() is False
        assert form.validate() is False

    assert form.form_errors == ["Acquisition fields cannot be changed here."]
