"""GET/POST /animals/new - create-animal flow."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from flask import Flask, url_for


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


def _csrf_token(response_data: bytes) -> str:
    match = re.search(
        rb'name="csrf_token" type="hidden" value="([^"]+)"',
        response_data,
    )
    assert match is not None
    return match.group(1).decode()


def _valid_payload(tank_id: Any, **overrides: Any) -> dict[str, str]:
    payload = {
        "name": "Mabel",
        "species": "Ocellaris clownfish",
        "scientific_name": "Amphiprion ocellaris",
        "sex": "female",
        "acquired_quantity": "2",
        "tank_id": str(tank_id),
        "acquired_at": "2026-04-28T14:30",
        "notes": "Bonded pair.",
        "initial_note": "Acquired from local breeder.",
        "submit": "Save",
    }
    payload.update(overrides)
    return payload


def test_unauthenticated_redirects(client: Any) -> None:
    resp = client.get("/animals/new", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_get_renders_add_form(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.get("/animals/new")

    assert resp.status_code == 200
    assert b"Add animal" in resp.data
    assert b'action="/animals/new"' in resp.data
    assert b'name="csrf_token"' in resp.data
    assert b'name="species"' in resp.data
    assert bytes(str(tank.id), "utf-8") in resp.data


def test_post_persists_animal_and_acquired_event_atomically(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType

    user = _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        "/animals/new",
        data=_valid_payload(tank.id),
        follow_redirects=False,
    )

    assert resp.status_code == 302
    animal = db_session.scalar(select(Animal).where(Animal.species == "Ocellaris clownfish"))
    assert animal is not None
    assert resp.location == url_for("animals.detail_animal", animal_id=animal.id)
    assert animal.name == "Mabel"
    assert animal.scientific_name == "Amphiprion ocellaris"
    assert animal.sex == "female"
    assert animal.acquired_quantity == 2
    assert animal.notes == "Bonded pair."

    events = list(
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == animal.id)).all()
    )
    assert len(events) == 1
    event = events[0]
    assert event.event_type == EventType.ACQUIRED.value
    assert event.tank_id == tank.id
    assert event.quantity_delta == 2
    assert event.occurred_at == datetime(2026, 4, 28, 14, 30, tzinfo=UTC)
    assert event.note == "Acquired from local breeder."
    assert event.recorded_by_user_id == user.id


def test_tank_query_param_preselects(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    other = _seed_tank(db_session, name="Frag 20")
    selected = _seed_tank(db_session, name="Lagoon 40")

    resp = client.get(f"/animals/new?tank={selected.id}")

    assert resp.status_code == 200
    assert bytes(f'value="{other.id}"', "utf-8") in resp.data
    assert re.search(
        bytes(rf'<option[^>]*value="{selected.id}"[^>]*selected', "utf-8"),
        resp.data,
    ) or re.search(
        bytes(rf'<option[^>]*selected[^>]*value="{selected.id}"', "utf-8"),
        resp.data,
    )


def test_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)

    resp = client.post(
        "/animals/new",
        data=_valid_payload(tank.id),
        follow_redirects=False,
    )

    assert resp.status_code == 400


def test_csrf_accepts_valid_token(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    form_resp = client.get("/animals/new")
    payload = _valid_payload(tank.id, csrf_token=_csrf_token(form_resp.data))

    resp = client.post("/animals/new", data=payload, follow_redirects=False)

    assert resp.status_code == 302
