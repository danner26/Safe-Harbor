"""Config classes for the Safe Harbor Flask app.

12-factor: every config value comes from an env var with a sensible dev default.
Production hard-fails on missing/insecure required vars.

**Import-order contract:** env vars are read at *module import time*. Callers MUST
ensure env is fully loaded before importing this module — via python-dotenv (in
dev), `env_file:` directives in docker-compose, or by injecting env BEFORE
launching gunicorn. After import, class attributes are frozen; runtime
``monkeypatch.setenv(...)`` will NOT re-evaluate them. ``ProdConfig.validate()``
reads env live as a defense-in-depth check at app-factory time, which is why
its body uses ``os.getenv(...)`` rather than ``cls.SECRET_KEY``.
"""

from __future__ import annotations

import logging
import os
from datetime import timedelta
from typing import ClassVar

_logger = logging.getLogger(__name__)

_TRUTHY = frozenset({"1", "true", "yes", "on", "y", "t"})
_FALSY = frozenset({"0", "false", "no", "off", "n", "f", ""})


def _safe_float_env(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        _logger.warning(
            "config: %s=%r is not parseable as float; using default %r",
            name,
            raw,
            default,
        )
        return default


def _safe_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in _TRUTHY:
        return True
    if normalized in _FALSY:
        return False
    _logger.warning(
        "config: %s=%r is not a recognized boolean; using default %r",
        name,
        raw,
        default,
    )
    return default


class BaseConfig:
    """Common defaults; subclasses override per environment."""

    DEBUG: ClassVar[bool] = False
    TESTING: ClassVar[bool] = False
    ENABLE_DEV_ROUTES: ClassVar[bool] = False

    SECRET_KEY: ClassVar[str] = os.getenv("SECRET_KEY", "change-me-in-prod")
    DEV_VISUAL_ADMIN_PASSWORD: ClassVar[str] = os.getenv("DEV_VISUAL_ADMIN_PASSWORD", "")

    SQLALCHEMY_DATABASE_URI: ClassVar[str] = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://safeharbor:safeharbor@localhost:5432/safeharbor",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: ClassVar[bool] = False

    UPLOAD_DIR: ClassVar[str] = os.environ.get("UPLOAD_DIR", "/data/uploads")
    MAX_CONTENT_LENGTH: ClassVar[int] = 15 * 1024 * 1024

    REDIS_URL: ClassVar[str] = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    SMTP_HOST: ClassVar[str] = os.getenv("SMTP_HOST", "localhost")
    SMTP_PORT: ClassVar[int] = int(os.getenv("SMTP_PORT", "1025"))
    SMTP_USER: ClassVar[str] = os.getenv("SMTP_USER", "")
    SMTP_PASS: ClassVar[str] = os.getenv("SMTP_PASS", "")
    SMTP_FROM: ClassVar[str] = os.getenv("SMTP_FROM", "safeharbor@localhost")

    STORAGE_DIR: ClassVar[str] = os.getenv("STORAGE_DIR", "./uploads")

    LOG_LEVEL: ClassVar[str] = os.getenv("LOG_LEVEL", "INFO")
    TRUST_PROXY_HEADERS: ClassVar[bool] = _safe_bool_env("TRUST_PROXY_HEADERS", False)
    UPLOAD_DIR_REQUIRE_WRITABLE: ClassVar[bool] = _safe_bool_env(
        "UPLOAD_DIR_REQUIRE_WRITABLE", True
    )
    SENTRY_DSN: ClassVar[str] = os.getenv("SENTRY_DSN", "")
    SENTRY_TRACES_SAMPLE_RATE: ClassVar[float] = _safe_float_env(
        "SENTRY_TRACES_SAMPLE_RATE",
        0.0,
    )

    WTF_CSRF_ENABLED: ClassVar[bool] = True
    SESSION_COOKIE_SECURE: ClassVar[bool] = False
    SESSION_COOKIE_HTTPONLY: ClassVar[bool] = True
    SESSION_COOKIE_SAMESITE: ClassVar[str] = "Lax"

    REMEMBER_COOKIE_DURATION: ClassVar[timedelta] = timedelta(days=30)
    REMEMBER_COOKIE_HTTPONLY: ClassVar[bool] = True
    REMEMBER_COOKIE_SAMESITE: ClassVar[str] = "Lax"

    SERVER_NAME: ClassVar[str | None] = os.getenv("SERVER_NAME") or None
    PREFERRED_URL_SCHEME: ClassVar[str] = os.getenv("PREFERRED_URL_SCHEME") or "https"


class DevConfig(BaseConfig):
    DEBUG: ClassVar[bool] = True
    ENABLE_DEV_ROUTES: ClassVar[bool] = True


class TestConfig(BaseConfig):
    TESTING: ClassVar[bool] = True
    ENABLE_DEV_ROUTES: ClassVar[bool] = True
    WTF_CSRF_ENABLED: ClassVar[bool] = False
    WTF_CSRF_SSL_STRICT: ClassVar[bool] = False
    SQLALCHEMY_DATABASE_URI: ClassVar[str] = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://safeharbor:safeharbor@localhost:5432/safeharbor_test",
    )


class ProdConfig(BaseConfig):
    SESSION_COOKIE_SECURE: ClassVar[bool] = True
    REMEMBER_COOKIE_SECURE: ClassVar[bool] = True

    @classmethod
    def validate(cls) -> None:
        """Raise RuntimeError if required prod env vars are missing or insecure."""
        if cls.ENABLE_DEV_ROUTES:
            raise RuntimeError("ENABLE_DEV_ROUTES must be false in production")
        secret = os.getenv("SECRET_KEY", "change-me-in-prod")
        if secret in ("", "change-me-in-prod"):
            raise RuntimeError("SECRET_KEY must be set to a real secret in production")
        rate = cls.SENTRY_TRACES_SAMPLE_RATE
        if not (0.0 <= rate <= 1.0):
            raise RuntimeError(f"SENTRY_TRACES_SAMPLE_RATE must be in [0.0, 1.0]; got {rate}")
        for name in ("DATABASE_URL", "REDIS_URL", "SMTP_HOST", "STORAGE_DIR"):
            if not os.getenv(name):
                raise RuntimeError(f"{name} must be set in production")


_CONFIG_BY_NAME: dict[str, type[BaseConfig]] = {
    "development": DevConfig,
    "production": ProdConfig,
    "testing": TestConfig,
}


def get_config(name: str) -> type[BaseConfig]:
    return _CONFIG_BY_NAME[name]
