"""Dev blueprint gating and visual-fixture credential tests."""

from __future__ import annotations

import pytest
from flask import Flask

from safeharbor import create_app
from safeharbor.blueprints.dev import dev_bp
from safeharbor.config import BaseConfig, DevConfig, ProdConfig, TestConfig


@pytest.fixture
def prod_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "a-real-secret-32-chars-or-more-12345")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("STORAGE_DIR", "/data")


def test_dev_route_flag_defaults_closed_and_only_dev_test_open() -> None:
    assert BaseConfig.ENABLE_DEV_ROUTES is False
    assert DevConfig.ENABLE_DEV_ROUTES is True
    assert TestConfig.ENABLE_DEV_ROUTES is True
    assert ProdConfig.ENABLE_DEV_ROUTES is False


def test_prod_config_validate_rejects_enabled_dev_routes(
    monkeypatch: pytest.MonkeyPatch, prod_env: None
) -> None:
    monkeypatch.setattr(ProdConfig, "ENABLE_DEV_ROUTES", True)

    with pytest.raises(RuntimeError, match="ENABLE_DEV_ROUTES"):
        ProdConfig.validate()


def test_app_factory_registers_dev_blueprint_only_when_enabled(prod_env: None) -> None:
    testing_app = create_app("testing")
    assert testing_app.config["ENABLE_DEV_ROUTES"] is True
    assert "dev.styleguide" in testing_app.view_functions

    prod_app = create_app("production")
    assert prod_app.config["ENABLE_DEV_ROUTES"] is False
    assert "dev.styleguide" not in prod_app.view_functions


def test_visual_admin_password_comes_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEV_VISUAL_ADMIN_PASSWORD", "env-visual-secret")

    app = create_app("testing")

    assert app.config["DEV_VISUAL_ADMIN_PASSWORD"] == "env-visual-secret"


def test_dev_routes_404_when_gate_is_off() -> None:
    app = Flask(__name__)
    app.config.update(ENABLE_DEV_ROUTES=False, TESTING=False)
    app.register_blueprint(dev_bp)

    client = app.test_client()

    dev_rules = [rule.rule for rule in app.url_map.iter_rules() if rule.endpoint.startswith("dev.")]
    assert dev_rules
    for rule in dev_rules:
        response = client.get(rule)
        assert response.status_code == 404
