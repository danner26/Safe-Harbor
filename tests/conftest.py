"""Shared pytest fixtures.

`app` — a configured Flask app in test mode.
`client` — a test client for HTTP requests.
`db_session` — a transactional DB session that rolls back per test."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from flask import Flask
from flask.testing import FlaskClient

from safeharbor import create_app
from safeharbor.config import BaseConfig, TestConfig
from safeharbor.extensions import db as _db

# Argon2 hash of "configured-password-12345", precomputed to avoid paying KDF cost
# in every test that needs a non-empty user row to bypass first-run setup. Tests
# that need to authenticate should seed their own user via _seed_user.
_CONFIGURED_USER_PASSWORD_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$+1+r1dr7H6O0dm6tdQ6BMA"
    "$qU2vhW6O//5JWV1lKAmsAmNypNKOo0LhImQillNBDe4"
)


@pytest.fixture(scope="session", autouse=True)
def _test_upload_dir(tmp_path_factory: pytest.TempPathFactory) -> Generator[Path, None, None]:
    upload_dir = tmp_path_factory.mktemp("upload-dir")
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(BaseConfig, "UPLOAD_DIR", str(upload_dir), raising=False)
        monkeypatch.setattr(TestConfig, "UPLOAD_DIR", str(upload_dir), raising=False)
        yield upload_dir


@pytest.fixture
def app() -> Generator[Flask, None, None]:
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()
        # Dispose the engine so its pooled connections are returned to the OS.
        # Without this, each test leaks ~5 connections to the SQLAlchemy pool;
        # CI's postgres hits max_connections=100 around the 20th test.
        _db.engine.dispose()


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def db_session(app: Flask) -> Generator[object, None, None]:
    """Wraps each test in a savepoint that rolls back at teardown."""
    with app.app_context():
        connection = _db.engine.connect()
        transaction = connection.begin()
        _db.session.configure(bind=connection)
        yield _db.session
        _db.session.remove()
        transaction.rollback()
        connection.close()


@pytest.fixture
def configured_user(db_session):
    """Seed a user so tests exercise normal app flow after first-run setup."""
    from safeharbor.models.account import User

    user = User(
        email="configured-user@x.com",
        password_hash=_CONFIGURED_USER_PASSWORD_HASH,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user
