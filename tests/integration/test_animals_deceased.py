"""POST /animals/<id>/deceased - animal deceased flow."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from flask import Flask


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
    quantity: int = 1,
) -> Any:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType

    animal = Animal(name=name, species=species, acquired_quantity=quantity)
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


def _csrf_token(response_data: bytes) -> str:
    match = re.search(
        rb'name="csrf_token" type="hidden" value="([^"]+)"',
        response_data,
    )
    assert match is not None
    return match.group(1).decode()


def _deceased_payload(**overrides: Any) -> dict[str, str]:
    payload = {
        "quantity": "1",
        "occurred_at": "2026-04-28T14:30",
        "note": "Found during morning check.",
        "submit": "Mark deceased",
    }
    payload.update({key: str(value) for key, value in overrides.items()})
    return payload


def test_unauthenticated_redirects_to_login(client: Any) -> None:
    resp = client.post(f"/animals/{uuid4()}/deceased", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_detail_renders_deceased_modal_with_current_count_default(
    client: Any, db_session: Any
) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank, quantity=2)

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert f'action="/animals/{animal.id}/deceased"' in body
    assert 'id="deceased-modal"' in body
    assert 'data-bs-target="#deceased-modal"' in body
    assert 'name="quantity"' in body
    assert 'value="2"' in body
    assert 'name="occurred_at"' in body
    assert 'name="note"' in body


def test_individual_full_deceased_tombstones(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent, EventType
    from safeharbor.services import animal_service

    user = _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank, quantity=1)

    resp = client.post(
        f"/animals/{animal.id}/deceased",
        data=_deceased_payload(quantity=1),
        follow_redirects=False,
    )

    assert resp.status_code == 302
    assert resp.location == f"/animals/{animal.id}"

    events = list(
        db_session.scalars(
            select(AnimalEvent)
            .where(AnimalEvent.animal_id == animal.id)
            .order_by(AnimalEvent.occurred_at.asc(), AnimalEvent.created_at.asc())
        ).all()
    )
    assert len(events) == 2
    event = events[1]
    assert event.event_type == EventType.DECEASED.value
    assert event.tank_id is None
    assert event.quantity_delta == -1
    assert event.occurred_at.replace(tzinfo=UTC) == datetime(2026, 4, 28, 14, 30, tzinfo=UTC)
    assert event.note == "Found during morning check."
    assert event.recorded_by_user_id == user.id
    assert animal_service.current_count(animal) == 0
    assert animal_service.is_alive(animal) is False
    assert animal_service.current_tank(animal) is None
    assert animal_service.animals_on_tank(tank) == []


def test_group_partial_deceased_drops_count(client: Any, db_session: Any) -> None:
    from safeharbor.services import animal_service

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank, quantity=3)

    resp = client.post(
        f"/animals/{animal.id}/deceased",
        data=_deceased_payload(quantity=2),
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Marked 2 deceased." in resp.data
    assert animal_service.current_count(animal) == 1
    assert animal_service.is_alive(animal) is True
    assert animal_service.animals_on_tank(tank) == [animal]


def test_group_total_deceased_tombstones(client: Any, db_session: Any) -> None:
    from safeharbor.services import animal_service

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank, quantity=3)

    resp = client.post(
        f"/animals/{animal.id}/deceased",
        data=_deceased_payload(quantity=3, note=""),
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Marked 3 deceased." in resp.data
    assert animal_service.current_count(animal) == 0
    assert animal_service.is_alive(animal) is False
    assert animal_service.current_tank(animal) is None
    assert animal_service.animals_on_tank(tank) == []


def test_overcount_rejected(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent, EventType
    from safeharbor.services import animal_service

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank, quantity=2)

    resp = client.post(
        f"/animals/{animal.id}/deceased",
        data=_deceased_payload(quantity=5),
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Deceased quantity cannot make current count negative." in resp.data
    events = list(
        db_session.scalars(
            select(AnimalEvent).where(
                AnimalEvent.animal_id == animal.id,
                AnimalEvent.event_type == EventType.DECEASED.value,
            )
        ).all()
    )
    assert events == []
    assert animal_service.current_count(animal) == 2
    assert animal_service.animals_on_tank(tank) == [animal]


def test_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.post(
        f"/animals/{animal.id}/deceased",
        data=_deceased_payload(),
        follow_redirects=False,
    )

    assert resp.status_code == 400


def test_csrf_accepts_valid_token(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)
    form_resp = client.get(f"/animals/{animal.id}")
    payload = _deceased_payload(quantity=1, csrf_token=_csrf_token(form_resp.data))

    resp = client.post(f"/animals/{animal.id}/deceased", data=payload, follow_redirects=False)

    assert resp.status_code == 302
