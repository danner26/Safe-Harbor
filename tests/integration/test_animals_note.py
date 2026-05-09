"""POST /animals/<id>/note - animal note flow."""

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


def _add_deceased_event(db_session: Any, animal: Any, *, quantity: int) -> None:
    from safeharbor.models.animal_event import AnimalEvent, EventType

    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.DECEASED.value,
            tank_id=None,
            quantity_delta=-quantity,
            occurred_at=datetime(2026, 4, 27, 8, 15, tzinfo=UTC),
            note="Found deceased.",
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


def _note_payload(**overrides: Any) -> dict[str, str]:
    payload = {
        "event_type": "health_note",
        "occurred_at": "2026-04-28T14:30",
        "note": "Eating aggressively and breathing normally.",
        "submit": "Add note",
    }
    payload.update({key: str(value) for key, value in overrides.items()})
    return payload


def test_unauthenticated_redirects_to_login(client: Any, configured_user) -> None:
    resp = client.post(f"/animals/{uuid4()}/note", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_detail_renders_inline_collapsible_note_form(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert f'action="/animals/{animal.id}/note"' in body
    assert 'href="?expand=note#add-note"' in body
    assert 'id="add-note"' in body
    assert "<details" in body
    assert re.search(r'<details id="add-note"[^>]* open', body) is None
    assert 'name="event_type"' in body
    assert 'value="health_note"' in body
    assert 'value="observation"' in body
    assert 'name="occurred_at"' in body
    assert 'name="note"' in body
    assert 'data-bs-target="#note-modal"' not in body
    assert 'id="note-modal"' not in body

    expanded_resp = client.get(f"/animals/{animal.id}?expand=note")

    assert expanded_resp.status_code == 200
    expanded_body = expanded_resp.data.decode()
    assert re.search(r'<details id="add-note"[^>]* open', expanded_body) is not None


def test_health_note_persists(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent, EventType

    user = _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.post(
        f"/animals/{animal.id}/note",
        data=_note_payload(),
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
    assert event.event_type == EventType.HEALTH_NOTE.value
    assert event.tank_id is None
    assert event.quantity_delta is None
    assert event.occurred_at.replace(tzinfo=UTC) == datetime(2026, 4, 28, 14, 30, tzinfo=UTC)
    assert event.note == "Eating aggressively and breathing normally."
    assert event.recorded_by_user_id == user.id


def test_observation_persists(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent, EventType

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.post(
        f"/animals/{animal.id}/note",
        data=_note_payload(
            event_type="observation",
            note="Started hosting the hammer coral.",
        ),
        follow_redirects=False,
    )

    assert resp.status_code == 302
    event = db_session.scalar(
        select(AnimalEvent).where(
            AnimalEvent.animal_id == animal.id,
            AnimalEvent.event_type == EventType.OBSERVATION.value,
        )
    )
    assert event is not None
    assert event.tank_id is None
    assert event.quantity_delta is None
    assert event.note == "Started hosting the hammer coral."


def test_note_after_tombstone_allowed(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent, EventType

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank, quantity=1)
    _add_deceased_event(db_session, animal, quantity=1)

    resp = client.post(
        f"/animals/{animal.id}/note",
        data=_note_payload(note="Final necropsy note."),
        follow_redirects=False,
    )

    assert resp.status_code == 302
    event = db_session.scalar(
        select(AnimalEvent).where(
            AnimalEvent.animal_id == animal.id,
            AnimalEvent.event_type == EventType.HEALTH_NOTE.value,
        )
    )
    assert event is not None
    assert event.note == "Final necropsy note."


def test_invalid_event_type_rejected(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent

    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.post(
        f"/animals/{animal.id}/note",
        data=_note_payload(event_type="moved"),
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Not a valid choice." in resp.data
    events = list(
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == animal.id)).all()
    )
    assert len(events) == 1


def test_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)

    resp = client.post(
        f"/animals/{animal.id}/note",
        data=_note_payload(),
        follow_redirects=False,
    )

    assert resp.status_code == 400


def test_csrf_accepts_valid_token(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    tank = _seed_tank(db_session)
    animal = _seed_animal(db_session, tank=tank)
    form_resp = client.get(f"/animals/{animal.id}")
    payload = _note_payload(csrf_token=_csrf_token(form_resp.data))

    resp = client.post(f"/animals/{animal.id}/note", data=payload, follow_redirects=False)

    assert resp.status_code == 302
