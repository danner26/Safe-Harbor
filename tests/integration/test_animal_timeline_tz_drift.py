"""Animal timeline timezone rendering for historical tank events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flask.testing import FlaskClient


def _login(client: FlaskClient, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="keeper@example.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_tank(
    db_session: Any,
    *,
    name: str,
    timezone: str,
) -> Any:
    from safeharbor.models.tank import Tank, WaterType

    tank = Tank(
        name=name,
        water_type=WaterType.SALT.value,
        timezone=timezone,
    )
    db_session.add(tank)
    db_session.flush()
    return tank


def test_timeline_renders_historical_tank_tz_for_non_pinned_events(
    client: FlaskClient,
    db_session: Any,
) -> None:
    from safeharbor.models.animal_event import EventType
    from safeharbor.services.animal_service import create_animal, move_animal, record_event

    user = _login(client, db_session)
    tank_a = _seed_tank(db_session, name="Tank A", timezone="UTC")
    tank_b = _seed_tank(db_session, name="Tank B", timezone="America/Los_Angeles")
    first_note = "First health note before west-coast move."
    second_note = "Second health note after west-coast move."

    animal = create_animal(
        name="Mabel",
        species="Ocellaris clownfish",
        scientific_name=None,
        sex=None,
        acquired_quantity=1,
        initial_tank=tank_a,
        acquired_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        initial_note="Acquired in Tank A.",
        recorded_by_user_id=user.id,
    )
    record_event(
        animal,
        event_type=EventType.HEALTH_NOTE,
        occurred_at=datetime(2026, 1, 1, 13, 0, tzinfo=UTC),
        note=first_note,
        recorded_by_user_id=user.id,
    )
    move_animal(
        animal,
        to_tank=tank_b,
        occurred_at=datetime(2026, 1, 2, 0, 0, tzinfo=UTC),
        note="Moved to Tank B.",
        recorded_by_user_id=user.id,
    )
    record_event(
        animal,
        event_type=EventType.HEALTH_NOTE,
        occurred_at=datetime(2026, 1, 2, 1, 0, tzinfo=UTC),
        note=second_note,
        recorded_by_user_id=user.id,
    )
    db_session.commit()

    response = client.get(f"/animals/{animal.id}")
    body = response.data.decode()

    assert response.status_code == 200
    assert first_note in body
    assert second_note in body
    assert body.index("Jan 1, 1:00 PM") < body.index(first_note)
    assert body.index("Jan 1, 5:00 PM") < body.index(second_note)
    assert body.index(first_note) < body.index("Moved to Tank B.") < body.index(second_note)
