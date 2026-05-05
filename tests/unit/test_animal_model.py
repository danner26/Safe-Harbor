"""Animal model - field shapes and CHECK constraints."""

from __future__ import annotations

from uuid import UUID

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from safeharbor.models import Animal as ExportedAnimal
from safeharbor.models import Sex as ExportedSex
from safeharbor.models.animal import Animal, Sex


def test_sex_enum_values() -> None:
    assert Sex.MALE.value == "male"
    assert Sex.FEMALE.value == "female"
    assert Sex.UNKNOWN.value == "unknown"


def test_animal_is_exported_from_models_package() -> None:
    assert ExportedAnimal is Animal
    assert ExportedSex is Sex


def test_animal_table_has_specified_columns_only(app, db_session) -> None:
    inspector = inspect(db_session.bind)
    columns = [column["name"] for column in inspector.get_columns("animals")]
    assert columns == [
        "id",
        "name",
        "species",
        "scientific_name",
        "sex",
        "acquired_quantity",
        "image_path",
        "notes",
        "created_at",
        "updated_at",
    ]


def test_animal_can_be_persisted_with_required_fields_only(app, db_session) -> None:
    animal = Animal(species="Amphiprion ocellaris", acquired_quantity=2)
    db_session.add(animal)
    db_session.commit()

    assert isinstance(animal.id, UUID)
    assert animal.name is None
    assert animal.scientific_name is None
    assert animal.sex is None
    assert animal.image_path is None
    assert animal.notes is None
    assert animal.created_at is not None
    assert animal.updated_at is not None


def test_animal_can_be_persisted_with_full_fields(app, db_session) -> None:
    animal = Animal(
        name="Mabel",
        species="Ocellaris clownfish",
        scientific_name="Amphiprion ocellaris",
        sex=Sex.FEMALE.value,
        acquired_quantity=1,
        image_path="animals/mabel.jpg",
        notes="Captive-bred juvenile.",
    )
    db_session.add(animal)
    db_session.commit()

    fetched = db_session.scalar(select(Animal).where(Animal.id == animal.id))
    assert fetched is not None
    assert fetched.name == "Mabel"
    assert fetched.species == "Ocellaris clownfish"
    assert fetched.scientific_name == "Amphiprion ocellaris"
    assert fetched.sex == "female"
    assert fetched.acquired_quantity == 1
    assert fetched.image_path == "animals/mabel.jpg"
    assert fetched.notes == "Captive-bred juvenile."


def test_animal_sex_check_constraint(app, db_session) -> None:
    bogus = Animal(species="Royal gramma", acquired_quantity=1, sex="pair")
    db_session.add(bogus)
    with pytest.raises(IntegrityError):
        db_session.commit()


def test_animal_acquired_quantity_check_constraint(app, db_session) -> None:
    bogus = Animal(species="Royal gramma", acquired_quantity=0)
    db_session.add(bogus)
    with pytest.raises(IntegrityError):
        db_session.commit()
