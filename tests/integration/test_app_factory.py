"""create_app() factory smoke tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from flask import Flask

from safeharbor import _validate_upload_dir, create_app


def test_create_app_returns_flask_instance() -> None:
    app = create_app("testing")
    assert isinstance(app, Flask)


def test_create_app_applies_test_config() -> None:
    app = create_app("testing")
    assert app.config["TESTING"] is True
    assert app.config["WTF_CSRF_ENABLED"] is False
    assert app.config["UPLOAD_DIR"]
    assert app.config["MAX_CONTENT_LENGTH"] == 15 * 1024 * 1024


def test_create_app_unknown_config_raises() -> None:
    with pytest.raises(KeyError):
        create_app("nonexistent")


def test_upload_dir_validation_raises_when_missing(
    tmp_path: Path,
) -> None:
    missing_upload_dir = tmp_path / "missing"
    app = Flask(__name__)
    app.config["UPLOAD_DIR"] = str(missing_upload_dir)

    with pytest.raises(RuntimeError, match="UPLOAD_DIR"):
        _validate_upload_dir(app)


def test_user_loader_returns_user_instance(app, db_session) -> None:
    from safeharbor.extensions import login_manager
    from safeharbor.models.account import User

    u = User(email="loader@x.com", password_hash="h")
    db_session.add(u)
    db_session.commit()

    loaded = login_manager._user_callback(str(u.id))
    assert loaded is not None
    assert loaded.id == u.id


def test_user_loader_returns_none_for_unknown_id(app) -> None:
    from uuid import uuid4

    from safeharbor.extensions import login_manager

    loaded = login_manager._user_callback(str(uuid4()))
    assert loaded is None


def test_display_volume_jinja_global_registered() -> None:
    from safeharbor import create_app

    app = create_app("testing")
    assert "display_volume" in app.jinja_env.globals


def test_safeharbor_version_jinja_global_present() -> None:
    app = create_app("testing")
    version = app.jinja_env.globals["safeharbor_version"]

    assert isinstance(version, str)
    assert version
