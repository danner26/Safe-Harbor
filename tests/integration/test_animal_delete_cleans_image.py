"""Animal pristine delete image cleanup integration tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _login(client: Any, db_session: Any) -> Any:
    from safeharbor.models.account import User
    from safeharbor.services.auth_service import hash_password

    user = User(email="animal-delete-cleanup@x.com", password_hash=hash_password("test-pw-12345"))
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user.id)
        sess["_fresh"] = True
    return user


def _seed_tank(db_session: Any) -> Any:
    from safeharbor.models.tank import Tank, WaterType

    tank = Tank(name="Reef 90", water_type=WaterType.SALT.value)
    db_session.add(tank)
    db_session.commit()
    return tank


def _seed_pristine_animal(db_session: Any, *, image_path: str | None = None) -> Any:
    from safeharbor.models.animal import Animal
    from safeharbor.models.animal_event import AnimalEvent, EventType

    tank = _seed_tank(db_session)
    animal = Animal(
        name="Mabel",
        species="Ocellaris clownfish",
        scientific_name="Amphiprion ocellaris",
        acquired_quantity=1,
        image_path=image_path,
    )
    db_session.add(animal)
    db_session.flush()
    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.ACQUIRED.value,
            tank_id=tank.id,
            quantity_delta=1,
            occurred_at=datetime(2026, 4, 29, 12, 30, tzinfo=UTC),
        )
    )
    db_session.commit()
    return animal


def _add_note_event(db_session: Any, animal: Any) -> None:
    from safeharbor.models.animal_event import AnimalEvent, EventType

    db_session.add(
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.OBSERVATION.value,
            tank_id=None,
            quantity_delta=None,
            occurred_at=datetime(2026, 4, 29, 13, 30, tzinfo=UTC),
            note="Eating well.",
        )
    )
    db_session.commit()


def test_pristine_delete_removes_file_from_disk(
    app: Any,
    client: Any,
    db_session: Any,
) -> None:
    from safeharbor.models.animal import Animal

    upload_dir = Path(app.config["UPLOAD_DIR"])
    _login(client, db_session)
    animal = _seed_pristine_animal(db_session)
    animal_id = animal.id
    image_path = upload_dir / "animals" / f"{animal_id}.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"stored image")

    resp = client.post(f"/animals/{animal_id}/delete", follow_redirects=False)

    assert resp.status_code == 302
    assert db_session.get(Animal, animal_id) is None
    assert not image_path.exists()


def test_pristine_delete_no_image_is_noop(
    app: Any,
    client: Any,
    db_session: Any,
) -> None:
    from safeharbor.models.animal import Animal

    upload_dir = Path(app.config["UPLOAD_DIR"])
    _login(client, db_session)
    animal = _seed_pristine_animal(db_session)
    animal_id = animal.id
    image_path = upload_dir / "animals" / f"{animal_id}.jpg"

    resp = client.post(f"/animals/{animal_id}/delete", follow_redirects=False)

    assert resp.status_code == 302
    assert db_session.get(Animal, animal_id) is None
    assert not image_path.exists()


def test_non_pristine_delete_keeps_file_and_animal(
    app: Any,
    client: Any,
    db_session: Any,
) -> None:
    from safeharbor.models.animal import Animal

    upload_dir = Path(app.config["UPLOAD_DIR"])
    _login(client, db_session)
    animal = _seed_pristine_animal(db_session)
    animal_id = animal.id
    image_path = upload_dir / "animals" / f"{animal_id}.jpg"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(b"stored image")
    _add_note_event(db_session, animal)

    resp = client.post(f"/animals/{animal_id}/delete", follow_redirects=True)

    assert resp.status_code == 200
    assert b"Animal must be pristine with exactly one acquired event." in resp.data
    assert db_session.get(Animal, animal_id) is not None
    assert image_path.exists()
