"""ProxyFix middleware tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from flask import Flask, request
from flask.testing import FlaskClient

from safeharbor import create_app
from safeharbor.config import BaseConfig, TestConfig


@pytest.fixture
def proxy_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Flask:
    monkeypatch.setattr(BaseConfig, "UPLOAD_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(TestConfig, "UPLOAD_DIR", str(tmp_path), raising=False)
    return create_app("testing")


def _add_url_probe(app: Flask) -> FlaskClient:
    def probe() -> str:
        return f"{request.scheme}|{request.host}"

    probe._is_public = True  # type: ignore[attr-defined]
    app.add_url_rule("/proxy-fix-probe", "proxy_fix_probe", probe)
    return app.test_client()


def test_proxy_fix_honors_x_forwarded_proto(proxy_app: Flask) -> None:
    client = _add_url_probe(proxy_app)

    response = client.get("/proxy-fix-probe", headers={"X-Forwarded-Proto": "https"})

    assert response.text == "https|localhost"


def test_proxy_fix_honors_x_forwarded_host(proxy_app: Flask) -> None:
    client = _add_url_probe(proxy_app)

    response = client.get("/proxy-fix-probe", headers={"X-Forwarded-Host": "app.example.test"})

    assert response.text == "https|app.example.test"


def test_proxy_fix_default_scheme_without_header(proxy_app: Flask) -> None:
    client = _add_url_probe(proxy_app)

    response = client.get("/proxy-fix-probe")

    assert response.text == "https|localhost"
