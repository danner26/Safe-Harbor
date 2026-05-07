"""Tests for Sentry initialization."""

from __future__ import annotations

from unittest.mock import patch

from flask import Flask
from sentry_sdk.integrations.flask import FlaskIntegration

from safeharbor import create_app
from safeharbor.config import BaseConfig, TestConfig
from safeharbor.extensions import init_sentry


def _app_with_sentry_config(dsn: str) -> Flask:
    app = Flask(__name__)
    app.config["SENTRY_DSN"] = dsn
    app.config["SENTRY_TRACES_SAMPLE_RATE"] = 0.25
    app.config["FLASK_CONFIG"] = "testing"
    return app


def test_init_sentry_noops_without_dsn() -> None:
    app = _app_with_sentry_config("")

    with patch("safeharbor.extensions.sentry_sdk.init") as sentry_init:
        init_sentry(app)

    sentry_init.assert_not_called()


def test_init_sentry_calls_sdk_with_dsn(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(BaseConfig, "UPLOAD_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(TestConfig, "UPLOAD_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(TestConfig, "SENTRY_DSN", "https://public@example.com/1", raising=False)
    monkeypatch.setattr(TestConfig, "SENTRY_TRACES_SAMPLE_RATE", 0.25, raising=False)
    with (
        patch("safeharbor.extensions._package_version", return_value="1.2.3"),
        patch("safeharbor.extensions.sentry_sdk.init") as sentry_init,
    ):
        create_app("testing")

    sentry_init.assert_called_once()
    kwargs = sentry_init.call_args.kwargs
    assert kwargs["dsn"] == "https://public@example.com/1"
    assert len(kwargs["integrations"]) == 1
    assert isinstance(kwargs["integrations"][0], FlaskIntegration)
    assert kwargs["environment"] == "testing"
    assert kwargs["traces_sample_rate"] == 0.25
    assert kwargs["send_default_pii"] is False
    assert kwargs["release"] == "1.2.3"
