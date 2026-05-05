"""Shared animal service test fixtures and seed helpers."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from flask import Flask

from safeharbor.extensions import db
from safeharbor.models.account import User
from safeharbor.models.animal import Animal, Sex
from safeharbor.models.animal_event import AnimalEvent, EventType
from safeharbor.models.tank import Tank, WaterType


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Flask, None, None]:
    from safeharbor import create_app
    from safeharbor.config import TestConfig

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(TestConfig, "UPLOAD_DIR", str(upload_dir), raising=False)

    app = create_app("testing")
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()
        db.engine.dispose()


def seed_tank_and_user(db_session) -> tuple[Tank, User]:
    tank = Tank(name="Reef 90", water_type=WaterType.SALT.value)
    user = User(email="keeper@example.com", password_hash="hash")
    db_session.add_all([tank, user])
    db_session.commit()
    return tank, user


def seed_animal_with_events(db_session) -> tuple[Animal, Tank, Tank, list[AnimalEvent]]:
    tank, user = seed_tank_and_user(db_session)
    second_tank = Tank(name="Frag 20", water_type=WaterType.SALT.value)
    animal = Animal(
        name="Mabel",
        species="Ocellaris clownfish",
        scientific_name=None,
        sex=Sex.FEMALE.value,
        acquired_quantity=5,
    )
    db_session.add_all([second_tank, animal])
    db_session.flush()

    events = [
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.ACQUIRED.value,
            tank_id=tank.id,
            quantity_delta=5,
            occurred_at=datetime(2026, 4, 29, 8, 0, tzinfo=UTC),
            recorded_by_user_id=user.id,
        ),
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.HEALTH_NOTE.value,
            tank_id=None,
            quantity_delta=None,
            occurred_at=datetime(2026, 4, 29, 8, 30, tzinfo=UTC),
            note="Eating well.",
            recorded_by_user_id=user.id,
        ),
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.MOVED.value,
            tank_id=second_tank.id,
            quantity_delta=None,
            occurred_at=datetime(2026, 4, 29, 9, 0, tzinfo=UTC),
            recorded_by_user_id=user.id,
        ),
        AnimalEvent(
            animal_id=animal.id,
            event_type=EventType.DECEASED.value,
            tank_id=None,
            quantity_delta=-1,
            occurred_at=datetime(2026, 4, 29, 10, 0, tzinfo=UTC),
            recorded_by_user_id=user.id,
        ),
    ]
    db_session.add_all(events)
    db_session.commit()
    return animal, tank, second_tank, events
