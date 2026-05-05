"""Config classes load env vars and apply correct defaults per environment."""

from __future__ import annotations

import pytest

from safeharbor.config import DevConfig, ProdConfig, TestConfig, get_config


def test_dev_config_has_debug_true() -> None:
    assert DevConfig.DEBUG is True
    assert DevConfig.TESTING is False


def test_test_config_has_testing_true() -> None:
    assert TestConfig.TESTING is True
    assert TestConfig.WTF_CSRF_ENABLED is False  # forms posted in tests w/o tokens


def test_prod_config_requires_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "change-me-in-prod")
    with pytest.raises(RuntimeError, match="SECRET_KEY"):
        ProdConfig.validate()


def test_prod_config_accepts_real_secret_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "a-real-secret-at-least-32-chars-long-1234")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("STORAGE_DIR", "/data")
    ProdConfig.validate()  # should not raise


def test_get_config_dispatches_by_name() -> None:
    assert get_config("development") is DevConfig
    assert get_config("production") is ProdConfig
    assert get_config("testing") is TestConfig


def test_base_config_remember_cookie_duration_is_30_days() -> None:
    from datetime import timedelta

    from safeharbor.config import BaseConfig

    assert timedelta(days=30) == BaseConfig.REMEMBER_COOKIE_DURATION


def test_prod_config_prefers_https_url_scheme() -> None:
    from safeharbor.config import ProdConfig

    assert ProdConfig.PREFERRED_URL_SCHEME == "https"


def test_dev_config_prefers_http_url_scheme() -> None:
    from safeharbor.config import DevConfig

    assert DevConfig.PREFERRED_URL_SCHEME == "http"
