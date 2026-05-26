"""Config classes load env vars and apply correct defaults per environment."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from safeharbor.config import (
    DevConfig,
    ProdConfig,
    TestConfig,
    _safe_bool_env,
    _safe_float_env,
    _safe_int_env,
    get_config,
)


def test_dev_config_has_debug_true() -> None:
    assert DevConfig.DEBUG is True
    assert DevConfig.TESTING is False


def test_test_config_has_testing_true() -> None:
    assert TestConfig.TESTING is True
    assert TestConfig.WTF_CSRF_ENABLED is False  # forms posted in tests w/o tokens
    assert TestConfig.WTF_CSRF_SSL_STRICT is False


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


def test_safe_float_env_warns_on_invalid(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "not-a-float")

    with caplog.at_level(logging.WARNING, logger="safeharbor.config"):
        value = _safe_float_env("SENTRY_TRACES_SAMPLE_RATE", 0.0)

    assert value == 0.0
    assert any(
        record.levelno == logging.WARNING and "SENTRY_TRACES_SAMPLE_RATE" in record.message
        for record in caplog.records
    )


def test_safe_int_env_returns_default_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUMMY_INT_VAR", raising=False)
    assert _safe_int_env("DUMMY_INT_VAR", 1025) == 1025


def test_safe_int_env_returns_default_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUMMY_INT_VAR", "")
    assert _safe_int_env("DUMMY_INT_VAR", 1025) == 1025


def test_safe_int_env_parses_valid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUMMY_INT_VAR", "587")
    assert _safe_int_env("DUMMY_INT_VAR", 1025) == 587


def test_safe_int_env_warns_on_invalid(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DUMMY_INT_VAR", "not-a-port")

    with caplog.at_level(logging.WARNING, logger="safeharbor.config"):
        value = _safe_int_env("DUMMY_INT_VAR", 1025)

    assert value == 1025
    assert any(
        record.levelno == logging.WARNING and "DUMMY_INT_VAR" in record.message
        for record in caplog.records
    )


def test_prodconfig_validate_passes_without_smtp_host(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "a-real-secret-at-least-32-chars-long-1234")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("STORAGE_DIR", "/data")
    monkeypatch.delenv("SMTP_HOST", raising=False)

    with caplog.at_level(logging.WARNING, logger="safeharbor.config"):
        ProdConfig.validate()

    assert any(
        record.levelno == logging.WARNING and "SMTP_HOST" in record.message
        for record in caplog.records
    )


def test_prodconfig_validate_still_fails_on_missing_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "a-real-secret-at-least-32-chars-long-1234")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("STORAGE_DIR", "/data")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        ProdConfig.validate()


def test_prodconfig_validate_no_warning_when_smtp_host_set(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SECRET_KEY", "a-real-secret-at-least-32-chars-long-1234")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("STORAGE_DIR", "/data")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")

    with caplog.at_level(logging.WARNING, logger="safeharbor.config"):
        ProdConfig.validate()

    assert not any(
        record.levelno == logging.WARNING and "SMTP_HOST" in record.message
        for record in caplog.records
    )


@pytest.mark.parametrize(
    "raw_value",
    ["1", "true", "yes", "on", "y", "t", "TRUE", "Yes", "  on  "],
)
def test_safe_bool_env_recognizes_truthy_values(
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    monkeypatch.setenv("DUMMY_BOOL_VAR", raw_value)

    assert _safe_bool_env("DUMMY_BOOL_VAR", False) is True


@pytest.mark.parametrize(
    "raw_value",
    ["0", "false", "no", "off", "n", "f", "", "FALSE", "  no  "],
)
def test_safe_bool_env_recognizes_falsy_values_silently(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
) -> None:
    monkeypatch.setenv("DUMMY_BOOL_VAR", raw_value)

    with caplog.at_level(logging.WARNING, logger="safeharbor.config"):
        value = _safe_bool_env("DUMMY_BOOL_VAR", True)

    assert value is False
    assert not caplog.records


@pytest.mark.parametrize("raw_value", ["flase", "yess", "truth", "maybe"])
@pytest.mark.parametrize("default", [True, False])
def test_safe_bool_env_warns_on_invalid(
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
    raw_value: str,
    default: bool,
) -> None:
    monkeypatch.setenv("DUMMY_BOOL_VAR", raw_value)

    with caplog.at_level(logging.WARNING, logger="safeharbor.config"):
        value = _safe_bool_env("DUMMY_BOOL_VAR", default)

    assert value is default
    assert any(
        record.levelno == logging.WARNING and "DUMMY_BOOL_VAR" in record.message
        for record in caplog.records
    )


def test_base_config_remember_cookie_duration_is_30_days() -> None:
    from datetime import timedelta

    from safeharbor.config import BaseConfig

    assert timedelta(days=30) == BaseConfig.REMEMBER_COOKIE_DURATION


def test_prod_config_prefers_https_url_scheme() -> None:
    env = {**os.environ}
    env.pop("PREFERRED_URL_SCHEME", None)
    command = (
        "from safeharbor.config import BaseConfig, ProdConfig; "
        "print(BaseConfig.PREFERRED_URL_SCHEME, ProdConfig.PREFERRED_URL_SCHEME)"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "https https"


def test_dev_config_prefers_https_url_scheme() -> None:
    env = {**os.environ}
    env.pop("PREFERRED_URL_SCHEME", None)
    command = (
        "from safeharbor.config import BaseConfig, DevConfig; "
        "print(BaseConfig.PREFERRED_URL_SCHEME, DevConfig.PREFERRED_URL_SCHEME)"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "https https"


def test_trust_proxy_headers_typo_fails_closed() -> None:
    env = {**os.environ, "TRUST_PROXY_HEADERS": "flase"}
    command = "from safeharbor.config import BaseConfig; print(BaseConfig.TRUST_PROXY_HEADERS)"

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "False"


def test_upload_dir_require_writable_typo_falls_back_to_default() -> None:
    env = {**os.environ, "UPLOAD_DIR_REQUIRE_WRITABLE": "fasle"}
    command = (
        "from safeharbor.config import BaseConfig; print(BaseConfig.UPLOAD_DIR_REQUIRE_WRITABLE)"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "True"


@pytest.mark.parametrize(
    "raw_value",
    ["1", "true", "yes", "on", "TRUE", "Yes", "  on  "],
)
def test_trust_proxy_headers_whitelist_truthy(raw_value: str) -> None:
    env = {**os.environ, "TRUST_PROXY_HEADERS": raw_value}
    command = "from safeharbor.config import BaseConfig; print(BaseConfig.TRUST_PROXY_HEADERS)"

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "True"


def test_server_name_and_preferred_url_scheme_flow_from_env_into_app_config(
    tmp_path: Path,
) -> None:
    env = {
        **os.environ,
        "SERVER_NAME": "example.test",
        "PREFERRED_URL_SCHEME": "http",
        "UPLOAD_DIR": str(tmp_path),
    }
    command = (
        "from safeharbor import create_app; "
        "app = create_app('testing'); "
        "print(app.config['SERVER_NAME'], app.config['PREFERRED_URL_SCHEME'])"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "example.test http"


def test_empty_server_name_becomes_none_and_url_scheme_defaults_to_https(tmp_path: Path) -> None:
    env = {
        **os.environ,
        "SERVER_NAME": "",
        "UPLOAD_DIR": str(tmp_path),
    }
    env.pop("PREFERRED_URL_SCHEME", None)
    command = (
        "from safeharbor import create_app; "
        "app = create_app('testing'); "
        "print(repr(app.config['SERVER_NAME']), app.config['PREFERRED_URL_SCHEME'])"
    )

    result = subprocess.run(
        [sys.executable, "-c", command],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.stdout.strip() == "None https"
