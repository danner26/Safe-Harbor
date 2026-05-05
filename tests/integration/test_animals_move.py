"""POST /animals/<id>/move - animal move flow."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
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


def _seed_tank(
    db_session: Any,
    *,
    name: str = "Reef 90",
    decommissioned: bool = False,
) -> Any:
    from safeharbor.models.tank import Tank, WaterType

    tank = Tank(
        name=name,
        water_type=WaterType.SALT.value,
        decommission_date=date(2026, 4, 28) if decommissioned else None,
    )
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_animal(
    db_session: Any,
    *,
    tank: Any,
    quantity: int = 2,
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


def _move_payload(to_tank_id: Any, **overrides: Any) -> dict[str, str]:
    payload = {
        "to_tank_id": str(to_tank_id),
        "occurred_at": "2026-04-28T14:30",
        "note": "Moved after quarantine.",
        "submit": "Move",
    }
    payload.update({key: str(value) for key, value in overrides.items()})
    return payload


def test_unauthenticated_redirects_to_login(client: Any) -> None:
    resp = client.post(f"/animals/{uuid4()}/move", follow_redirects=False)

    assert resp.status_code == 302
    assert "/login" in resp.location


def test_detail_renders_move_dropdown_with_active_tanks_only(client: Any, db_session: Any) -> None:
    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    lagoon = _seed_tank(db_session, name="Lagoon 40")
    decommissioned = _seed_tank(db_session, name="Retired 10", decommissioned=True)
    animal = _seed_animal(db_session, tank=reef)

    resp = client.get(f"/animals/{animal.id}")

    assert resp.status_code == 200
    body = resp.data.decode()
    assert f'action="/animals/{animal.id}/move"' in body
    assert 'data-action="move"' in body
    assert 'name="to_tank_id"' in body
    assert str(lagoon.id) in body
    assert "Lagoon 40" in body
    assert str(decommissioned.id) not in body
    assert "Retired 10" not in body


def test_move_writes_event_and_changes_current_tank(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent, EventType
    from safeharbor.services import animal_service

    user = _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    lagoon = _seed_tank(db_session, name="Lagoon 40")
    animal = _seed_animal(db_session, tank=reef)

    resp = client.post(
        f"/animals/{animal.id}/move",
        data=_move_payload(lagoon.id),
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
    assert event.event_type == EventType.MOVED.value
    assert event.tank_id == lagoon.id
    assert event.quantity_delta is None
    assert event.occurred_at.replace(tzinfo=UTC) == datetime(2026, 4, 28, 14, 30, tzinfo=UTC)
    assert event.note == "Moved after quarantine."
    assert event.recorded_by_user_id == user.id
    current_tank = animal_service.current_tank(animal)
    assert current_tank is not None
    assert current_tank.id == lagoon.id


def test_move_to_decommissioned_tank_rejected(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent
    from safeharbor.services import animal_service

    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    retired = _seed_tank(db_session, name="Retired 10", decommissioned=True)
    animal = _seed_animal(db_session, tank=reef)

    resp = client.post(
        f"/animals/{animal.id}/move",
        data=_move_payload(retired.id),
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Not a valid choice." in resp.data
    events = list(
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == animal.id)).all()
    )
    assert len(events) == 1
    current_tank = animal_service.current_tank(animal)
    assert current_tank is not None
    assert current_tank.id == reef.id


def test_move_to_decommissioned_tank_rejected_at_form_layer(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent, EventType

    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    retired = _seed_tank(db_session, name="Retired 10", decommissioned=True)
    animal = _seed_animal(db_session, tank=reef)

    resp = client.post(
        f"/animals/{animal.id}/move",
        data=_move_payload(retired.id),
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Not a valid choice." in resp.data
    moved_events = list(
        db_session.scalars(
            select(AnimalEvent).where(
                AnimalEvent.animal_id == animal.id,
                AnimalEvent.event_type == EventType.MOVED.value,
            )
        ).all()
    )
    assert moved_events == []


def test_move_on_tombstoned_rejected(client: Any, db_session: Any) -> None:
    from sqlalchemy import select

    from safeharbor.models.animal_event import AnimalEvent

    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    lagoon = _seed_tank(db_session, name="Lagoon 40")
    animal = _seed_animal(db_session, tank=reef, quantity=2)
    _add_deceased_event(db_session, animal, quantity=4)

    resp = client.post(
        f"/animals/{animal.id}/move",
        data=_move_payload(lagoon.id),
        follow_redirects=True,
    )

    assert resp.status_code == 200
    assert b"Animal must be alive to move." in resp.data
    events = list(
        db_session.scalars(select(AnimalEvent).where(AnimalEvent.animal_id == animal.id)).all()
    )
    assert len(events) == 2


def test_csrf_required(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    lagoon = _seed_tank(db_session, name="Lagoon 40")
    animal = _seed_animal(db_session, tank=reef)

    resp = client.post(
        f"/animals/{animal.id}/move",
        data=_move_payload(lagoon.id),
        follow_redirects=False,
    )

    assert resp.status_code == 400


def test_csrf_accepts_valid_token(app: Flask, client: Any, db_session: Any) -> None:
    app.config["WTF_CSRF_ENABLED"] = True
    _login(client, db_session)
    reef = _seed_tank(db_session, name="Reef 90")
    lagoon = _seed_tank(db_session, name="Lagoon 40")
    animal = _seed_animal(db_session, tank=reef)
    form_resp = client.get(f"/animals/{animal.id}")
    payload = _move_payload(lagoon.id, csrf_token=_csrf_token(form_resp.data))

    resp = client.post(f"/animals/{animal.id}/move", data=payload, follow_redirects=False)

    assert resp.status_code == 302
