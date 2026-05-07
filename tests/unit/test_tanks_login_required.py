"""Tank route login redirect tests."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from flask import Flask
from flask.testing import FlaskClient

from safeharbor import create_app
from safeharbor.blueprints.tanks import views as tank_views
from safeharbor.config import BaseConfig, TestConfig


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Flask, None, None]:
    """Create a lightweight app for redirect-only route assertions."""
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(BaseConfig, "UPLOAD_DIR", str(upload_dir), raising=False)
    monkeypatch.setattr(TestConfig, "UPLOAD_DIR", str(upload_dir), raising=False)
    yield create_app("testing")


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def assert_login_redirect(response, expected_next: str) -> None:  # type: ignore[no-untyped-def]
    assert response.status_code == 302
    location = response.headers["Location"]
    parsed = urlparse(location)
    assert parsed.path == "/login"
    qs = parse_qs(parsed.query)
    next_values = qs.get("next")
    assert next_values is not None
    next_target = urlparse(next_values[0])
    assert next_target.path == expected_next
    assert next_target.query == ""


def assert_explicit_login_required(view_name: str) -> None:
    view = getattr(tank_views, view_name)
    assert getattr(view, "__wrapped__", None) is not None


def test_new_tank_requires_login(client: FlaskClient) -> None:
    assert_explicit_login_required("new_tank")
    response = client.get("/tanks/new")
    assert_login_redirect(response, "/tanks/new")


def test_create_tank_requires_login(client: FlaskClient) -> None:
    assert_explicit_login_required("create_tank")
    response = client.post("/tanks")
    assert_login_redirect(response, "/tanks")


def test_edit_tank_requires_login(client: FlaskClient) -> None:
    assert_explicit_login_required("edit")
    tank_id = "00000000-0000-0000-0000-000000000001"
    response = client.get(f"/tanks/{tank_id}/edit")
    assert_login_redirect(response, f"/tanks/{tank_id}/edit")


def test_update_tank_requires_login(client: FlaskClient) -> None:
    assert_explicit_login_required("update_tank")
    tank_id = "00000000-0000-0000-0000-000000000001"
    response = client.post(f"/tanks/{tank_id}")
    assert_login_redirect(response, f"/tanks/{tank_id}")
