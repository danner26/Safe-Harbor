"""Integration coverage for a full backup, wipe, and restore cycle."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import select, text

from safeharbor.extensions import db as _db
from safeharbor.models.account import User
from safeharbor.models.base import new_id
from safeharbor.models.measurement import Measurement
from safeharbor.models.parameter_type import ParameterType
from safeharbor.models.tank import Tank
from safeharbor.models.unit import Unit
from safeharbor.services.auth_service import hash_password


def _assert_testing_config(app: Flask) -> None:
    assert app.config["TESTING"] is True
    assert app.config["SQLALCHEMY_DATABASE_URI"].endswith("/safeharbor_test")


@pytest.fixture
def db() -> SQLAlchemy:
    return _db


def _truncate_seed_tables(app: Flask, db: SQLAlchemy) -> None:
    _assert_testing_config(app)
    db.session.execute(text("TRUNCATE TABLE measurements, tanks, users CASCADE"))
    db.session.commit()


def _flask_env(app: Flask) -> dict[str, str]:
    return {
        **os.environ,
        "FLASK_APP": os.environ.get("FLASK_APP", "safeharbor.wsgi:app"),
        "FLASK_CONFIG": "testing",
        "DATABASE_URL": app.config["SQLALCHEMY_DATABASE_URI"],
        "TEST_DATABASE_URL": app.config["SQLALCHEMY_DATABASE_URI"],
        "UPLOAD_DIR": str(app.config["UPLOAD_DIR"]),
    }


@pytest.fixture
def seed_user_tank_measurement(
    db: SQLAlchemy, app: Flask
) -> Generator[tuple[UUID, UUID, UUID], None, None]:
    user_id = new_id()
    unit_id = new_id()
    parameter_type_id = new_id()
    tank_id = new_id()
    measurement_id = new_id()
    password_hash = hash_password("backup-cycle-password")
    user = User(
        id=user_id,
        email="backup-cycle@example.com",
        username="Backup Keeper",
        password_hash=password_hash,
        timezone="America/New_York",
    )
    unit = Unit(id=unit_id, code="t9ppm", display="ppm", dimension="concentration")
    parameter_type = ParameterType(
        id=parameter_type_id,
        key="t9nitrate",
        display_name="T9 Nitrate",
        canonical_unit_id=unit_id,
        applies_to_water_type="fresh",
        display_order=1,
    )
    tank = Tank(
        id=tank_id,
        name="Restore Cycle Tank",
        water_type="fresh",
        profile_key="tropical_fw_community",
        timezone="America/New_York",
        created_by_user_id=user_id,
    )
    measurement = Measurement(
        id=measurement_id,
        tank_id=tank_id,
        parameter_type_id=parameter_type_id,
        value=Decimal("12.3400"),
        recorded_at=datetime(2026, 5, 7, 12, 30, tzinfo=UTC),
        source="manual",
        recorded_by_user_id=user_id,
        note="backup cycle seed",
    )

    with app.app_context():
        _assert_testing_config(app)
        db.session.add_all([user, unit])
        db.session.flush()
        db.session.add_all([parameter_type, tank])
        db.session.flush()
        db.session.add(measurement)
        db.session.commit()
        yield user_id, tank_id, measurement_id
        _truncate_seed_tables(app, db)


@pytest.fixture
def seed_uploads(
    app: Flask, tmp_path_factory: pytest.TempPathFactory
) -> Generator[tuple[Path, dict[str, bytes]], None, None]:
    unique_dir = tmp_path_factory.mktemp("upload-seed").name
    seed_dir = Path(app.config["UPLOAD_DIR"]) / f"test_seed_{unique_dir}"
    expected_bytes = {"a.bin": b"alpha-bytes", "b.bin": b"beta-bytes"}
    seed_dir.mkdir(parents=True)
    for filename, content in expected_bytes.items():
        (seed_dir / filename).write_bytes(content)

    yield seed_dir, expected_bytes
    shutil.rmtree(seed_dir, ignore_errors=True)


@pytest.fixture
def tarball_path(tmp_path: Path) -> Path:
    return tmp_path / "test-backup-cycle.tar"


def test_full_backup_restore_cycle(
    app: Flask,
    db: SQLAlchemy,
    seed_user_tank_measurement: tuple[UUID, UUID, UUID],
    seed_uploads: tuple[Path, dict[str, bytes]],
    tarball_path: Path,
) -> None:
    user_id, tank_id, measurement_id = seed_user_tank_measurement
    seed_dir, expected_upload_bytes = seed_uploads
    seed_dir_name = seed_dir.name
    original_user = db.session.scalar(select(User).where(User.id == user_id))
    assert original_user is not None
    original_password_hash = original_user.password_hash

    subprocess.run(
        ["flask", "safeharbor", "backup", "--output", str(tarball_path)],
        env=_flask_env(app),
        check=True,
        capture_output=True,
    )

    assert tarball_path.exists()
    assert tarball_path.stat().st_size > 0
    with tarfile.open(tarball_path, "r") as tf:
        members = {member.name for member in tf.getmembers()}
    assert "db.dump" in members
    assert f"uploads/{seed_dir_name}/a.bin" in members
    assert f"uploads/{seed_dir_name}/b.bin" in members

    _truncate_seed_tables(app, db)
    shutil.rmtree(seed_dir)
    db.session.remove()

    assert db.session.scalar(select(User).where(User.id == user_id)) is None
    assert seed_dir.exists() is False
    db.session.remove()
    db.engine.dispose()

    subprocess.run(
        ["flask", "safeharbor", "restore", "--from", str(tarball_path), "--yes"],
        env=_flask_env(app),
        check=True,
        capture_output=True,
    )
    db.session.remove()

    restored_user = db.session.scalar(select(User).where(User.id == user_id))
    assert restored_user is not None
    assert restored_user.email == "backup-cycle@example.com"
    assert restored_user.password_hash == original_password_hash
    assert restored_user.timezone == "America/New_York"

    restored_tank = db.session.scalar(select(Tank).where(Tank.id == tank_id))
    assert restored_tank is not None
    assert restored_tank.created_by_user_id == user_id
    assert restored_tank.timezone == "America/New_York"
    assert restored_tank.water_type == "fresh"
    assert restored_tank.profile_key == "tropical_fw_community"

    restored_measurement = db.session.scalar(
        select(Measurement).where(Measurement.id == measurement_id)
    )
    assert restored_measurement is not None
    assert restored_measurement.tank_id == tank_id
    assert restored_measurement.recorded_by_user_id == user_id
    assert restored_measurement.value == Decimal("12.3400")

    for filename, content in expected_upload_bytes.items():
        assert (seed_dir / filename).read_bytes() == content
