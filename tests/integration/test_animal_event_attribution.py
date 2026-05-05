"""Animal detail timeline attribution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from flask.testing import FlaskClient
from sqlalchemy import event as sqla_event


def _login(
    client: FlaskClient,
    db_session: Any,
    *,
    email: str = "viewer@example.com",
    username: str | None = "viewer",
) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email=email, username=username, password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_animal_event(
    db_session: Any,
    *,
    recorded_by_user_id: Any,
    note: str = "Settled into the quarantine tank.",
) -> Any:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType
    from safeharbor.models.tank import Tank, WaterType

    tank = Tank(name="Quarantine", water_type=WaterType.SALT.value)
    animal = Animal(name="Mabel", species="Ocellaris clownfish", acquired_quantity=1)
    db_session.add_all([tank, animal])
    db_session.flush()
    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.ACQUIRED.value,
            tank_id=tank.id,
            quantity_delta=1,
            occurred_at=datetime(2026, 5, 1, 10, 0, tzinfo=UTC),
            note=note,
            recorded_by_user_id=recorded_by_user_id,
        )
    )
    db_session.commit()
    return animal


def test_unauthenticated_redirects_to_login(client: FlaskClient) -> None:
    response = client.get(f"/animals/{uuid4()}", follow_redirects=False)

    assert response.status_code == 302
    assert "/login" in response.location


def test_event_shows_logged_by_username(client: FlaskClient, db_session: Any) -> None:
    _login(client, db_session)
    recorder = _login(
        client,
        db_session,
        email="historian@example.com",
        username="historian",
    )
    animal = _seed_animal_event(db_session, recorded_by_user_id=recorder.id)

    response = client.get(f"/animals/{animal.id}")
    body = response.data.decode()

    assert response.status_code == 200
    assert "Settled into the quarantine tank." in body
    assert 'class="muted animal-event-attribution"' in body
    assert "logged by historian" in body


def test_event_with_no_recorder_omits_attribution(
    client: FlaskClient,
    db_session: Any,
) -> None:
    _login(client, db_session)
    animal = _seed_animal_event(db_session, recorded_by_user_id=None)

    response = client.get(f"/animals/{animal.id}")
    body = response.data.decode()

    assert response.status_code == 200
    assert "Settled into the quarantine tank." in body
    assert "animal-event-attribution" not in body


def test_lifecycle_rows_no_n_plus_one(app, db_session: Any) -> None:
    from safeharbor.models.account import User
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType
    from safeharbor.models.tank import Tank, WaterType
    from safeharbor.services import animal_service
    from safeharbor.services.auth_service import hash_password

    tank = Tank(name="Display Reef", water_type=WaterType.SALT.value)
    animal = Animal(name="Dot", species="Clown goby", acquired_quantity=6)
    recorders = [
        User(
            email=f"keeper{index}@example.com",
            username=f"keeper{index}",
            password_hash=hash_password("test-pw-12345"),
        )
        for index in range(6)
    ]
    db_session.add_all([tank, animal, *recorders])
    db_session.flush()
    db_session.add_all(
        [
            AnimalEvent(
                animal_id=animal.id,
                event_type=EventType.ACQUIRED.value,
                tank_id=tank.id,
                quantity_delta=1,
                occurred_at=datetime(2026, 5, 1, 10, index, tzinfo=UTC),
                recorded_by_user_id=recorder.id,
            )
            for index, recorder in enumerate(recorders)
        ]
    )
    db_session.commit()
    query_count = 0

    def count_query(*args: object) -> None:
        nonlocal query_count
        query_count += 1

    sqla_event.listen(db_session.get_bind(), "before_cursor_execute", count_query)
    try:
        rows = animal_service.lifecycle_rows(animal)
    finally:
        sqla_event.remove(db_session.get_bind(), "before_cursor_execute", count_query)

    assert [row["logged_by_display"] for row in rows] == [
        f"logged by keeper{index}" for index in range(6)
    ]
    assert query_count == 2
