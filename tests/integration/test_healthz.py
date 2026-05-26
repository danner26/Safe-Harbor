"""/healthz returns 200 with three sub-checks."""

from __future__ import annotations


def test_healthz_returns_200(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_payload_shape(client) -> None:
    response = client.get("/healthz")
    body = response.get_json()
    assert body["status"] == "ok"
    assert "db" in body
    assert "redis" in body


def test_healthz_db_check_green(client) -> None:
    response = client.get("/healthz")
    body = response.get_json()
    assert body["db"] == "ok"


def test_healthz_reports_email_disabled_when_smtp_unset(client, monkeypatch) -> None:
    monkeypatch.delenv("SMTP_HOST", raising=False)
    response = client.get("/healthz")
    body = response.get_json()
    assert body["email"] == "disabled"


def test_healthz_reports_email_configured_when_smtp_set(client, monkeypatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    response = client.get("/healthz")
    body = response.get_json()
    assert body["email"] == "configured"
