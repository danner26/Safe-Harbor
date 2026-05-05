"""/dev/styleguide is available in dev/test, hidden in production."""

from __future__ import annotations

import pytest


def test_styleguide_returns_200_in_test_config(client) -> None:
    response = client.get("/dev/styleguide")
    assert response.status_code == 200


def test_styleguide_renders_color_swatches(client) -> None:
    response = client.get("/dev/styleguide")
    body = response.data
    # Spot-check a few tokens
    assert b"--surface" in body
    assert b"--accent" in body
    assert b"--success" in body


def test_styleguide_renders_components(client) -> None:
    response = client.get("/dev/styleguide")
    body = response.data
    assert b"badge-success" in body
    assert b"btn-primary" in body
    assert b"chip-salt" in body
    assert b"kpi-card" in body or b"kpi-grid" in body  # KPI cards present


def test_styleguide_404_in_production_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "a-real-secret-32-chars-or-more-12345")
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("REDIS_URL", "redis://x")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("STORAGE_DIR", "/data")
    from safeharbor import create_app

    app = create_app("production")
    client = app.test_client()
    response = client.get("/dev/styleguide")
    assert response.status_code == 404
